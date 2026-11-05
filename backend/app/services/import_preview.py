"""Work out what an import WOULD do. Changes nothing.

The colonel sees this before he commits: how many families are new, which
existing records would change and in what way, which rows look like duplicates,
and which rows have problems.
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
    signature_for_duplicate_check,
)
from app.models.custom_field import EXTRA_PREFIX
from app.services.children import child_differences, match_child, sheet_children
from app.services.row_parser import ParsedRow, apply_overrides, parse_row


class RowAction(str, Enum):
    create = "create"  # a family we do not have
    update = "update"  # changes an existing family
    unchanged = "unchanged"  # we already have this, nothing differs
    needs_decision = "needs_decision"  # might be an existing family, not sure
    duplicate_in_file = "duplicate_in_file"  # the same person twice in this sheet
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


@dataclass
class FieldChange:
    field_name: str
    label: str
    old_value: str | None
    new_value: str | None


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


@dataclass
class ImportPreview:
    total_rows: int
    counts: dict[str, int]
    rows: list[RowPreview]
    problem_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "counts": self.counts,
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
                )
            )

    for key, column in FAMILY_FIELDS.items():
        new_value = row.values.get(key)
        if new_value is None or new_value == "":
            continue  # the sheet says nothing, so leave what we have
        old_value = getattr(family, column, None)
        if not same_value(old_value, new_value):
            changes.append(
                FieldChange(column, _label(key), _as_text(old_value), _as_text(new_value))
            )

    soldier = family.soldier
    if soldier is not None:
        for key, column in SOLDIER_FIELDS.items():
            new_value = row.values.get(key)
            if new_value is None or new_value == "":
                continue
            old_value = getattr(soldier, column, None)
            if not same_value(old_value, new_value):
                changes.append(
                    FieldChange(
                        f"soldier.{column}",
                        _label(key),
                        _as_text(old_value),
                        _as_text(new_value),
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
                )
            )

    return changes


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
    seen_signatures: dict[str, int] = {}
    problem_count = 0

    total = len(sheet.rows)
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
        if preview.problems:
            problem_count += 1

        # He asked for this row to be left out. Say so, and stop here.
        if parsed.skipped_by_user:
            preview.action = RowAction.excluded
            rows.append(preview)
            continue

        if parsed.has_blocking_problem:
            preview.action = RowAction.skipped
            preview.problems.append(
                {
                    "field": "widow_name",
                    "code": "missing_name",
                    "severity": "high",
                    "message": "No widow's name and no soldier's name â€” nothing to go on",
                }
            )
            rows.append(preview)
            continue

        # The same person appearing twice in this one sheet.
        signature = signature_for_duplicate_check(parsed)
        if signature and signature in seen_signatures:
            preview.action = RowAction.duplicate_in_file
            preview.duplicate_of_row = seen_signatures[signature]
            rows.append(preview)
            continue
        if signature:
            seen_signatures[signature] = row_number

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
            preview.action = (
                RowAction.update if preview.changes else RowAction.unchanged
            )
        elif match.is_uncertain:
            preview.action = RowAction.needs_decision
        else:
            preview.action = RowAction.create

        rows.append(preview)

    counts = {action.value: 0 for action in RowAction}
    for row in rows:
        counts[row.action.value] += 1

    return ImportPreview(
        total_rows=len(rows),
        counts=counts,
        rows=rows,
        problem_count=problem_count,
    )
