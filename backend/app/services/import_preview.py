"""Work out what an import WOULD do. Changes nothing.

The colonel sees this before he commits: how many families are new, which
existing records would change and in what way, which rows look like duplicates,
and which rows have problems.

Nothing about an existing family changes without his say. Every value that
would change (an update, or a likely typo) needs his choice: keep the
database value, take the sheet's, or type the right one. A row that only
might be a family we have needs him to say whether it is.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Family
from app.services.excel_reader import SheetData
from app.services.matching import (
    Candidate,
    FamilyIndex,
    SheetIndex,
    facts_of,
)
from app.models.custom_field import EXTRA_PREFIX
from app.services.children import child_differences, match_child, sheet_children
from app.services.row_parser import ParsedRow, apply_overrides, parse_row
from app.services.typos import typo_reason


class RowAction(str, Enum):
    create = "create"  # a family we do not have
    update = "update"  # changes an existing family
    possible_typo = "possible_typo"  # changes an existing family, some changes look like typos
    unchanged = "unchanged"  # we already have this, nothing differs
    needs_decision = "needs_decision"  # might be an existing family, not sure
    duplicate_in_file = "duplicate_in_file"  # an exact copy of an earlier row in this sheet
    lookalike_in_file = "lookalike_in_file"  # might be the same family as an earlier row
    skipped = "skipped"  # too little to work with
    excluded = "excluded"  # he asked for this row to be left out


# Which parsed field goes where. (model, column name)
FAMILY_FIELDS = {
    "widow_name": "primary_contact_name",
    "nok_relationship": "nok_relationship",
    "phone": "primary_phone",
    "alternate_phone": "alternate_phone",
    "email": "email",
    "village_or_town": "village_or_town",
    "town": "town",
    "tehsil": "tehsil",
    "post_office": "post_office",
    "district": "district",
    "state": "state",
    "pincode": "pincode",
    "geolocation": "gps_coordinates",
    "ppo_number": "ppo_number",
    "bank_account_number": "bank_account_number",
    "bank_ifsc": "bank_ifsc",
    "bank_name": "bank_name",
    "bank_branch": "bank_branch",
    "bank_account_holder": "bank_account_holder",
    "bank_address": "bank_address",
    "co_unit_name": "co_unit_name",
    "co_unit_phone": "co_unit_phone",
    "record_office": "record_office",
    "correspondence_address": "correspondence_address",
    "correspondence_pincode": "correspondence_pincode",
    "annual_income": "annual_income",
    "monthly_pension_amount": "monthly_pension_amount",
    "notes": "notes",
}

SOLDIER_FIELDS = {
    "soldier_name": "full_name",
    "rank": "rank",
    "service_number": "service_number",
    "unit": "unit",
    "regiment": "regiment",
    "date_of_death": "date_of_death",
    "cause_category": "cause_category",
    "cause_sub_category": "cause_sub_category",
    "place_of_death": "place_of_death",
}

# Child fields (child1_name, child2_dob, ...) are read and shown in the
# preview, but written to separate child records rather than to the family.


# What he chose for one changed value.
KEEP, EXCEL, TYPED = "keep", "excel", "typed"
# What he chose for a row that might be a family we have.
SAME, NEW, LEAVE = "same", "new", "leave"
# What he chose for two rows of this sheet that look like one family:
# keep the earlier row only, this row only, or both as different families.
FIRST, SECOND, BOTH = "first", "second", "both"
# Two rows this alike are worth asking about (the same floor as the database check).
LOOKALIKE_SCORE = 40


@dataclass
class FieldChange:
    field_name: str
    label: str
    old_value: str | None
    new_value: str | None
    # The sheet field it comes from ("phone", "child1_dob"), for typing a correction.
    field_key: str = ""
    # Why it looks like a typo ("Only 1 digit different"), or None for a real update.
    typo: str | None = None
    # keep / excel / typed, or None while he hasn't chosen.
    decision: str | None = None


@dataclass
class EditableField:
    """One value from this row, as it would be written."""

    field_key: str
    label: str
    value: str
    edited: bool


@dataclass
class RowPreview:
    row_number: int
    action: RowAction
    widow_name: str | None
    soldier_name: str | None
    district: str | None
    # Everything this row would write, so he can correct any of it.
    fields: list[EditableField] = field(default_factory=list)
    edited_fields: list[str] = field(default_factory=list)
    skipped_by_user: bool = False
    matched_family_id: int | None = None
    matched_family_code: str | None = None
    match_score: int = 0
    match_reasons: list[str] = field(default_factory=list)
    other_matches: list[dict[str, Any]] = field(default_factory=list)
    changes: list[FieldChange] = field(default_factory=list)
    problems: list[dict[str, str]] = field(default_factory=list)
    duplicate_of_row: int | None = None
    # For a possible duplicate: same / new / leave, or None while undecided.
    match_choice: str | None = None
    # For a possible duplicate: the sheet and the database side by side.
    comparison: list[dict[str, str | None]] = field(default_factory=list)
    # How many choices this row still needs from him.
    undecided: int = 0
    # Another row of this sheet it looks like, and how alike (0-100).
    pair_with_row: int | None = None
    pair_score: int = 0
    pair_reasons: list[str] = field(default_factory=list)
    # first / second / both, or None while undecided.
    pair_choice: str | None = None
    # The two rows side by side: "excel" is the other row, "database" this one.
    pair_comparison: list[dict[str, str | None]] = field(default_factory=list)
    # A plain sentence about why this row is where it is, when it isn't obvious.
    note: str | None = None


@dataclass
class ImportPreview:
    total_rows: int
    counts: dict[str, int]
    rows: list[RowPreview]
    problem_count: int
    # Rows still waiting for his choice, by group. Import is refused until 0.
    undecided: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "counts": self.counts,
            "undecided": self.undecided,
            "problem_count": self.problem_count,
            "rows": [
                {**asdict(r), "action": r.action.value} for r in self.rows
            ],
        }


def same_value(old: object, new: object) -> bool:
    """True when two values only differ in capitals or spacing.

    The colonel's sheet is in capitals ("WIFE", "KALANAUR"). Without this,
    every re-import would report changes that are not changes.
    """
    a, b = _as_text(old), _as_text(new)
    if a is None or b is None:
        return a == b
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):  # an Enum
        return str(value.value)
    if hasattr(value, "strftime"):  # a date â€” show it the Indian way
        return value.strftime("%d-%m-%Y")
    return str(value)


def _label(field_key: str) -> str:
    from app.services.column_mapping import TARGET_BY_KEY

    target = TARGET_BY_KEY.get(field_key)
    if target:
        return target.label
    return field_key.replace("_", " ").capitalize()


def diff_against_family(
    row: ParsedRow,
    family: Family,
    extra_labels: dict[str, str] | None = None,
) -> list[FieldChange]:
    """Only fields that would actually change. Blanks never overwrite."""
    changes: list[FieldChange] = []
    labels = extra_labels or {}

    # Extra fields live in the family's pocket, not in a column of their own.
    existing_extras = family.extra_fields or {}
    for key, new_value in row.extra_fields.items():
        if not new_value:
            continue
        old_value = existing_extras.get(key)
        if not same_value(old_value, new_value):
            changes.append(
                FieldChange(
                    f"extra.{key}",
                    labels.get(key, key.replace("_", " ").capitalize()),
                    _as_text(old_value),
                    _as_text(new_value),
                    field_key=f"{EXTRA_PREFIX}{key}",
                )
            )

    for key, column in FAMILY_FIELDS.items():
        new_value = row.values.get(key)
        if new_value is None or new_value == "":
            continue  # the sheet says nothing, so leave what we have
        old_value = getattr(family, column, None)
        if not same_value(old_value, new_value):
            changes.append(
                FieldChange(
                    column, _label(key), _as_text(old_value), _as_text(new_value),
                    field_key=key,
                )
            )

    soldier = family.soldier
    if soldier is not None:
        for key, column in SOLDIER_FIELDS.items():
            # The category is worked out from the cause he wrote, and follows it.
            if key == "cause_category":
                continue
            new_value = row.values.get(key)
            if new_value is None or new_value == "":
                continue
            old_value = getattr(soldier, column, None)
            if not same_value(old_value, new_value):
                changes.append(
                    FieldChange(
                        f"soldier.{column}",
                        _label("cause_of_death" if key == "cause_sub_category" else key),
                        _as_text(old_value),
                        _as_text(new_value),
                        field_key="cause_of_death" if key == "cause_sub_category" else key,
                    )
                )

    # Children: a new child is shown as an addition, a known child as the
    # fields that would change. Children not in the sheet are left alone.
    taken: set[int] = set()
    for child in sheet_children(row.values):
        member = match_child(child, list(family.members), taken)
        if member is None:
            changes.append(
                FieldChange(
                    f"child.{child.slot}",
                    f"Child {child.slot}",
                    None,
                    f"{child.name} (new child)",
                    field_key=f"child{child.slot}_name",
                )
            )
            continue
        taken.add(member.id)
        for column, part, old, new in child_differences(child, member):
            changes.append(
                FieldChange(
                    f"child.{child.slot}.{column}",
                    f"Child {child.slot} {part}",
                    _as_text(old),
                    _as_text(new),
                    field_key=f"child{child.slot}_{CHILD_KEYS.get(column, column)}",
                )
            )

    return changes


# A child record's column -> the sheet field part (child1_dob, child1_sex).
CHILD_KEYS = {"full_name": "name", "date_of_birth": "dob", "gender": "sex"}


def decide_changes(
    changes: list[FieldChange], decisions: dict[str, str], typed: set[str]
) -> int:
    """Mark each change as a likely typo or not, and with his choice so far.

    A value he typed himself counts as decided. Returns how many changes are
    still waiting for a choice.
    """
    waiting = 0
    for change in changes:
        change.typo = typo_reason(change.field_name, change.old_value, change.new_value)
        if change.field_key in typed:
            change.decision = TYPED
        else:
            change.decision = decisions.get(change.field_name)
        if change.decision is None:
            waiting += 1
    return waiting


def side_by_side(row: ParsedRow, family: Family) -> list[dict[str, str | None]]:
    """The details that tell two families apart, the sheet next to the database.

    mark: "=" the same, "~" spelt or typed slightly differently, "!=" different,
    "" when one side is empty.
    """
    soldier = family.soldier
    pairs = [
        ("Name of NOK", "primary_contact_name", row.values.get("widow_name"), family.primary_contact_name),
        ("Soldier", "soldier.full_name", row.values.get("soldier_name"), soldier.full_name if soldier else None),
        ("Army number", "soldier.service_number", row.values.get("service_number"), soldier.service_number if soldier else None),
        ("Date of death", "soldier.date_of_death", row.values.get("date_of_death"), soldier.date_of_death if soldier else None),
        ("Relationship", "nok_relationship", row.values.get("nok_relationship"), family.nok_relationship),
        ("Phone", "primary_phone", row.values.get("phone"), family.primary_phone),
        ("Village", "village_or_town", row.values.get("village_or_town"), family.village_or_town),
        ("District", "district", row.values.get("district"), family.district),
        ("State", "state", row.values.get("state"), family.state),
    ]
    out: list[dict[str, str | None]] = []
    for label, name, sheet_value, db_value in pairs:
        excel, database = _as_text(sheet_value), _as_text(db_value)
        if not excel and not database:
            continue
        if not excel or not database:
            mark = ""
        elif same_value(excel, database):
            mark = "="
        elif typo_reason(name, database, excel):
            mark = "~"
        else:
            mark = "!="
        out.append({"label": label, "excel": excel, "database": database, "mark": mark})
    return out


def same_row(a: ParsedRow, b: ParsedRow) -> bool:
    """Every value the same (ignoring capitals and spacing): an exact copy."""
    keys = set(a.values) | set(b.values)
    extras = set(a.extra_fields) | set(b.extra_fields)
    return all(same_value(a.values.get(k), b.values.get(k)) for k in keys) and all(
        same_value(a.extra_fields.get(k), b.extra_fields.get(k)) for k in extras
    )


def rows_side_by_side(first: ParsedRow, second: ParsedRow) -> list[dict[str, str | None]]:
    """Two sheet rows next to each other, marked as in side_by_side.

    "excel" holds the earlier row and "database" this one, so the screen can
    reuse one table; the labels on screen say which row is which.
    """
    pairs = [
        ("Name of NOK", "primary_contact_name", "widow_name"),
        ("Soldier", "soldier.full_name", "soldier_name"),
        ("Army number", "soldier.service_number", "service_number"),
        ("Date of death", "soldier.date_of_death", "date_of_death"),
        ("Relationship", "nok_relationship", "nok_relationship"),
        ("Phone", "primary_phone", "phone"),
        ("Village", "village_or_town", "village_or_town"),
        ("District", "district", "district"),
        ("State", "state", "state"),
    ]
    out: list[dict[str, str | None]] = []
    for label, name, key in pairs:
        a, b = _as_text(first.values.get(key)), _as_text(second.values.get(key))
        if not a and not b:
            continue
        if not a or not b:
            mark = ""
        elif same_value(a, b):
            mark = "="
        elif typo_reason(name, a, b):
            mark = "~"
        else:
            mark = "!="
        out.append({"label": label, "excel": a, "database": b, "mark": mark})
    return out


def _candidate_dict(candidate: Candidate) -> dict[str, Any]:
    return {
        "family_id": candidate.family_id,
        "family_code": candidate.family_code,
        "score": candidate.score,
        "reasons": candidate.reasons,
    }


def extra_field_labels(session: Session) -> dict[str, str]:
    """{key: label} for every approved extra field, for readable previews."""
    from sqlalchemy import select

    from app.models import CustomField

    return {
        field.key: field.label
        for field in session.scalars(select(CustomField)).all()
    }


def row_override(
    overrides: dict[str, dict],
    added_fields: dict[str, str],
    row_number: int,
) -> dict | None:
    """The corrections that apply to one row.

    An added field's value for every row comes first; a correction typed on
    that row wins over it. Both count as typed by him, not read from the file.
    """
    own = overrides.get(str(row_number)) or {}
    defaults = {k: v for k, v in (added_fields or {}).items() if v not in (None, "")}
    if not own and not defaults:
        return None
    return {
        "skip": own.get("skip", False),
        "values": {**defaults, **(own.get("values") or {})},
    }


def editable_fields(
    row: ParsedRow,
    mapping: dict[str, str],
    extra_labels: dict[str, str],
    headers: list[str] | None = None,
    added_keys: list[str] | None = None,
) -> list[EditableField]:
    """What this row would write, in the order the sheet lists it.

    The saved mapping cannot be trusted for order (the database stores it as
    JSON and sorts the keys), so the sheet's own heading order is used.
    """
    out: list[EditableField] = []
    seen: set[str] = set()
    ordered = [mapping.get(h) for h in headers] if headers else list(mapping.values())
    # Fields he added on the preview come after the sheet's own columns.
    ordered += list(added_keys or [])

    for target in ordered:
        if not target or target == "__ignore__" or target in seen:
            continue
        seen.add(target)

        if target.startswith(EXTRA_PREFIX):
            key = target[len(EXTRA_PREFIX) :]
            value = row.extra_fields.get(key, "")
            label = extra_labels.get(key, key.replace("_", " ").capitalize())
        elif target == "cause_of_death":
            value = _as_text(row.values.get("cause_sub_category")) or ""
            label = _label(target)
        else:
            value = _as_text(row.values.get(target)) or ""
            label = _label(target)

        out.append(
            EditableField(
                field_key=target,
                label=label,
                value=value,
                edited=target in row.edited_fields,
            )
        )
    return out


def build_preview(
    session: Session,
    sheet: SheetData,
    mapping: dict[str, str],
    overrides: dict[str, dict] | None = None,
    added_fields: dict[str, str] | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ImportPreview:
    """What importing this sheet would do, row by row. Writes nothing.

    `on_progress("checking", done, total)` is called as rows are checked, so
    the screen can show a progress bar.
    """
    index = FamilyIndex(session)
    labels = extra_field_labels(session)
    overrides = overrides or {}
    added_fields = added_fields or {}
    added_keys = list(added_fields)
    families_by_id = {f.id: f for f in index.families}

    rows: list[RowPreview] = []
    problem_count = 0
    # Rows that go on to be compared with the database: (preview, parsed, his choices).
    to_match: list[tuple[RowPreview, ParsedRow, dict]] = []

    # 1. Read every row, with his corrections.
    total = len(sheet.rows)
    readable: list[tuple[RowPreview, ParsedRow, dict]] = []
    for position, raw_row in enumerate(sheet.rows):
        if on_progress:
            on_progress("checking", position + 1, total)
        # +1 for the heading row, +1 because people count from one.
        row_number = (sheet.header_row_number or 1) + position + 1
        parsed = parse_row(raw_row, mapping, sheet.headers, row_number)
        apply_overrides(parsed, row_override(overrides, added_fields, row_number))

        preview = RowPreview(
            row_number=row_number,
            action=RowAction.skipped,
            widow_name=_as_text(parsed.values.get("widow_name")),
            soldier_name=_as_text(parsed.values.get("soldier_name")),
            district=_as_text(parsed.values.get("district")),
            fields=editable_fields(parsed, mapping, labels, sheet.headers, added_keys),
            edited_fields=sorted(parsed.edited_fields),
            skipped_by_user=parsed.skipped_by_user,
            problems=[
                {
                    "field": p.field_name,
                    "code": p.code.value,
                    "severity": p.severity.value,
                    "message": p.message,
                }
                for p in parsed.problems
            ],
        )
        rows.append(preview)
        if preview.problems:
            problem_count += 1

        # He asked for this row to be left out. Say so, and stop here.
        if parsed.skipped_by_user:
            preview.action = RowAction.excluded
            continue

        if parsed.has_blocking_problem:
            preview.action = RowAction.skipped
            preview.problems.append(
                {
                    "field": "widow_name",
                    "code": "missing_name",
                    "severity": "high",
                    "message": "No widow's name and no soldier's name — nothing to go on",
                }
            )
            continue
        readable.append((preview, parsed, overrides.get(str(row_number)) or {}))

    # 2. The same family twice in this sheet. An exact copy is skipped by
    #    itself; rows that only look alike wait for him to say which to keep.
    sheet_index = SheetIndex()
    by_position: dict[int, tuple[RowPreview, ParsedRow, dict]] = {}
    dropped: set[int] = set()
    for position, (preview, parsed, own) in enumerate(readable):
        facts = facts_of(position, parsed)
        found = sheet_index.best(facts)
        if found and found[1] >= LOOKALIKE_SCORE:
            earlier_facts, score, reasons = found
            earlier, earlier_parsed, _ = by_position[earlier_facts.position]
            if same_row(parsed, earlier_parsed):
                preview.action = RowAction.duplicate_in_file
                preview.duplicate_of_row = earlier.row_number
                preview.note = f"An exact copy of row {earlier.row_number}, so it is skipped."
                continue

            preview.pair_with_row = earlier.row_number
            preview.pair_score = score
            preview.pair_reasons = reasons
            preview.pair_comparison = rows_side_by_side(earlier_parsed, parsed)
            preview.pair_choice = own.get("pair")
            if preview.pair_choice is None:
                preview.action = RowAction.lookalike_in_file
                preview.undecided = 1
            elif preview.pair_choice == FIRST:
                preview.action = RowAction.excluded
                preview.note = f"Left out: you kept row {earlier.row_number} for this family."
                continue
            elif preview.pair_choice == SECOND:
                dropped.add(earlier.row_number)
                earlier.action = RowAction.excluded
                earlier.note = f"Left out: you kept row {preview.row_number} for this family."

        sheet_index.add(facts)
        by_position[position] = (preview, parsed, own)

    for preview, parsed, own in by_position.values():
        if preview.row_number not in dropped and preview.action != RowAction.lookalike_in_file:
            to_match.append((preview, parsed, own))

    # 3. Each row left is compared with the families we already have.
    for preview, parsed, own in to_match:
        decisions = own.get("decisions") or {}
        typed = set(parsed.edited_fields)

        match = index.find(parsed)
        if match.best:
            preview.matched_family_id = match.best.family_id
            preview.matched_family_code = match.best.family_code
            preview.match_score = match.best.score
            preview.match_reasons = match.best.reasons
            preview.other_matches = [_candidate_dict(c) for c in match.others]

        if match.is_confident and match.best:
            family = families_by_id[match.best.family_id]
            preview.changes = diff_against_family(parsed, family, labels)
            preview.undecided = decide_changes(preview.changes, decisions, typed)
            if not preview.changes:
                preview.action = RowAction.unchanged
            elif any(c.typo for c in preview.changes):
                preview.action = RowAction.possible_typo
            else:
                preview.action = RowAction.update
        elif match.is_uncertain and match.best:
            family = families_by_id[match.best.family_id]
            preview.action = RowAction.needs_decision
            preview.comparison = side_by_side(parsed, family)
            preview.match_choice = own.get("match")
            if preview.match_choice == SAME:
                # He says it is that family: its changes need his choice too.
                preview.changes = diff_against_family(parsed, family, labels)
                preview.undecided = decide_changes(preview.changes, decisions, typed)
            elif preview.match_choice is None:
                preview.undecided = 1
        else:
            preview.action = RowAction.create


    counts = {action.value: 0 for action in RowAction}
    undecided: dict[str, int] = {}
    for row in rows:
        counts[row.action.value] += 1
        if row.undecided:
            undecided[row.action.value] = undecided.get(row.action.value, 0) + 1

    return ImportPreview(
        total_rows=len(rows),
        counts=counts,
        rows=rows,
        problem_count=problem_count,
        undecided=undecided,
    )
