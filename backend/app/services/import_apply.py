"""Actually write the rows, once he has confirmed the preview.

The rule from the brief: family data is never overwritten silently. Every
single changed field writes a FieldHistory row first â€” old value, new value,
which file it came from, when, and who did it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    CustomField,
    DataQualityIssue,
    Family,
    FamilyMember,
    FieldHistory,
    ImportBatch,
    Soldier,
)
from app.models.enums import ChangeSource, IssueCode, IssueSeverity, IssueStatus, Relation
from app.services.excel_reader import SheetData
from app.services.import_preview import (
    FAMILY_FIELDS,
    row_override,
    same_value,
    SOLDIER_FIELDS,
    RowAction,
    build_preview,
)
from app.services.children import (
    child_differences,
    match_child,
    new_member,
    sheet_children,
)
from app.services.row_parser import apply_overrides, parse_row

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ImportOutcome:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    excluded: int = 0  # rows he chose to leave out
    fields_corrected: int = 0  # values he typed over before importing
    duplicates_flagged: int = 0
    needs_decision: int = 0
    fields_changed: int = 0
    issues_raised: int = 0
    new_family_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "excluded": self.excluded,
            "fields_corrected": self.fields_corrected,
            "duplicates_flagged": self.duplicates_flagged,
            "needs_decision": self.needs_decision,
            "fields_changed": self.fields_changed,
            "issues_raised": self.issues_raised,
            "new_family_codes": self.new_family_codes[:50],
        }


def _apply_children(
    session: Session,
    family: Family,
    parsed,
    batch: ImportBatch,
    now: datetime,
) -> int:
    """Add or update the children in this row. Returns fields changed.

    A child already on record is matched and updated, never added twice.
    A child not in the sheet is left alone. Every change is recorded with
    its old value, the same as any family field.
    """
    changed = 0
    taken: set[int] = set()
    members = list(family.members)

    for child in sheet_children(parsed.values):
        member = match_child(child, members, taken)
        if member is None:
            member = new_member(family.id, child)
            session.add(member)
            session.flush()
            members.append(member)
            taken.add(member.id)
            _history(
                session, "family_member", member.id, "__created__",
                None, child.name, batch, now,
            )
            changed += 1
            continue

        taken.add(member.id)
        for column, _part, old, new in child_differences(child, member):
            by_officer = f"child{child.slot}_{_child_key(column)}" in parsed.edited_fields
            _history(
                session, "family_member", member.id, column, old, new,
                batch, now, by_officer,
            )
            setattr(member, column, new)
            if column == "marital_status":
                member.is_married = child.is_married
            changed += 1
    return changed


def _child_key(column: str) -> str:
    """Member column -> the sheet field part, so corrections are credited."""
    return {
        "full_name": "name",
        "date_of_birth": "dob",
        "gender": "sex",
        "marital_status": "marital_status",
    }.get(column, column)


def point_from_gps(coordinates: str | None) -> str | None:
    """'28.613900, 77.209000' -> a map point. Latitude comes first, as written."""
    if not coordinates:
        return None
    try:
        lat_text, lon_text = (part.strip() for part in coordinates.split(","))
        lat, lon = float(lat_text), float(lon_text)
    except ValueError:
        return None
    return f"SRID=4326;POINT({lon:.6f} {lat:.6f})"


def relation_from_text(text: str | None) -> Relation:
    """The colonel's RELATIONSHIP column, e.g. 'WIFE', as a family relation."""
    value = (text or "").strip().lower()
    if value in {"wife", "widow", "spouse", "w/o"}:
        return Relation.widow
    if value == "mother":
        return Relation.mother
    if value == "father":
        return Relation.father
    if not value:
        return Relation.widow  # the usual case when the sheet leaves it blank
    return Relation.other_dependent


def next_family_code(session: Session) -> str:
    """AP-2026-0151, carrying on from whatever is already there.

    Only plain numeric codes count towards the highest number. Seeded
    duplicates use codes like AP-2026-D001, and a plain text MAX() would pick
    those first ('D' sorts after '9') and hand back a code already in use.
    """
    year = date.today().year
    prefix = f"AP-{year}-"

    existing = set(
        session.scalars(
            select(Family.family_code).where(Family.family_code.like(f"{prefix}%"))
        ).all()
    )
    highest = 0
    for code in existing:
        tail = code.removeprefix(prefix)
        if tail.isdigit():
            highest = max(highest, int(tail))

    # Belt and braces: never hand back a code that is already taken.
    number = highest + 1
    while f"{prefix}{number:04d}" in existing:
        number += 1
    return f"{prefix}{number:04d}"


def family_codes(session: Session):
    """AP-2026-0151, AP-2026-0152, ... handed out one by one for an import.

    Works out the highest code once, instead of re-reading every code for
    each new family (that made a big import slow, and slower as it went).
    """
    year = date.today().year
    prefix = f"AP-{year}-"
    existing = set(
        session.scalars(
            select(Family.family_code).where(Family.family_code.like(f"{prefix}%"))
        ).all()
    )
    highest = max(
        (int(code.removeprefix(prefix)) for code in existing if code.removeprefix(prefix).isdigit()),
        default=0,
    )
    number = highest
    while True:
        number += 1
        code = f"{prefix}{number:04d}"
        if code not in existing:  # never a code that is already taken
            yield code


# New families are written this many at a time: one trip to the database per
# table for the whole group, instead of several trips for every family.
SAVE_GROUP_SIZE = 200


@dataclass
class _NewFamily:
    """A family built in memory, waiting for its group to be saved."""

    family: Family
    code: str
    children: list[FamilyMember]
    row_number: int
    row_preview: Any
    problems: list[Any]


def _history(
    session: Session,
    entity_type: str,
    entity_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    batch: ImportBatch,
    when: datetime,
    by_officer: bool = False,
) -> None:
    """One row per changed field. This is the never-overwrite rule.

    A value the colonel typed over on the preview is recorded as coming from
    him, not from the file â€” otherwise the history would claim the sheet said
    something it never said.
    """
    session.add(
        FieldHistory(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=None if old_value is None else str(old_value),
            new_value=None if new_value is None else str(new_value),
            source=ChangeSource.officer_entry if by_officer else ChangeSource.excel_import,
            source_reference=f"import#{batch.id} {batch.original_filename}",
            changed_at=when,
            changed_by_user_id=batch.uploaded_by_user_id,
            note="Corrected on the preview screen" if by_officer else None,
        )
    )


def _raise_issue(
    session: Session,
    family_id: int | None,
    entity_type: str,
    entity_id: int,
    code: IssueCode,
    severity: IssueSeverity,
    description: str,
    details: dict[str, Any],
    when: datetime,
) -> None:
    session.add(
        DataQualityIssue(
            entity_type=entity_type,
            entity_id=entity_id,
            family_id=family_id,
            issue_code=code,
            severity=severity,
            status=IssueStatus.open,
            description=description,
            details=details,
            detected_at=when,
        )
    )


def _raise_row_problems(
    session: Session,
    family_id: int,
    row_number: int,
    problems: list[Any],
    batch: ImportBatch,
    now: datetime,
    outcome: ImportOutcome,
) -> None:
    """Problems found while reading a row become "needs attention" items."""
    for problem in problems:
        _raise_issue(
            session,
            family_id,
            "family",
            family_id,
            problem.code,
            problem.severity,
            f"Row {row_number}: {problem.message}",
            {
                "import_id": batch.id,
                "row_number": row_number,
                "field": problem.field_name,
                "raw_value": problem.raw_value,
            },
            now,
        )
        outcome.issues_raised += 1


def _save_group(
    session: Session,
    waiting: list[_NewFamily],
    batch: ImportBatch,
    now: datetime,
    outcome: ImportOutcome,
) -> None:
    """Save a group of new families in one go, then record their history.

    The history and "needs attention" rows need each family's id, which only
    exists once the family is saved, so they are added straight after.
    """
    if not waiting:
        return
    session.flush()
    for item in waiting:
        family = item.family
        for member in item.children:
            _history(
                session, "family_member", member.id, "__created__",
                None, member.full_name, batch, now,
            )
        _history(session, "family", family.id, "__created__", None, item.code, batch, now)

        # It might be the same family under a different spelling: say so.
        preview = item.row_preview
        if preview.action == RowAction.needs_decision:
            _raise_issue(
                session,
                family.id,
                "family",
                family.id,
                IssueCode.possible_duplicate,
                IssueSeverity.high,
                (
                    f"Row {item.row_number} may be the same family as "
                    f"{preview.matched_family_code}. Added as a new record, "
                    "needs an officer to decide."
                ),
                {
                    "other_family_id": preview.matched_family_id,
                    "other_family_code": preview.matched_family_code,
                    "score": preview.match_score,
                    "reasons": preview.match_reasons,
                    "import_id": batch.id,
                    "row_number": item.row_number,
                },
                now,
            )
            outcome.issues_raised += 1

        _raise_row_problems(
            session, family.id, item.row_number, item.problems, batch, now, outcome
        )
    session.flush()
    waiting.clear()


def apply_import(
    session: Session,
    batch: ImportBatch,
    sheet: SheetData,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ImportOutcome:
    """Write the sheet. Call only after the colonel has seen the preview.

    `on_progress(stage, done, total)` is called as it goes, so the screen can
    show a progress bar: first "checking" (the rows against saved families),
    then "saving".
    """
    mapping = batch.confirmed_mapping
    overrides = batch.row_overrides or {}
    added_fields = batch.added_fields or {}
    preview = build_preview(
        session, sheet, mapping, overrides, added_fields, on_progress=on_progress
    )
    outcome = ImportOutcome()
    now = datetime.now(IST)
    # Extra fields actually used by this sheet, so their usage count is honest.
    used_extra_keys: set[str] = set()
    # New families wait here until a group is full, then are saved together.
    waiting: list[_NewFamily] = []
    codes = family_codes(session)
    total = len(sheet.rows)

    previews_by_row = {p.row_number: p for p in preview.rows}

    for position, raw_row in enumerate(sheet.rows):
        if on_progress:
            on_progress("saving", position + 1, total)
        row_number = (sheet.header_row_number or 1) + position + 1
        row_preview = previews_by_row.get(row_number)
        if row_preview is None:
            continue

        parsed = parse_row(raw_row, mapping, sheet.headers, row_number)
        apply_overrides(parsed, row_override(overrides, added_fields, row_number))

        if row_preview.action == RowAction.excluded:
            outcome.excluded += 1
            continue

        if row_preview.action == RowAction.skipped:
            outcome.skipped += 1
            continue

        if row_preview.action == RowAction.duplicate_in_file:
            outcome.duplicates_flagged += 1
            continue

        if row_preview.action == RowAction.unchanged:
            outcome.unchanged += 1
            continue

        # --- an existing family changes ---
        if row_preview.action == RowAction.update and row_preview.matched_family_id:
            family = session.get(Family, row_preview.matched_family_id)
            if family is None:
                outcome.skipped += 1
                continue

            for key, column in FAMILY_FIELDS.items():
                new_value = parsed.values.get(key)
                if new_value is None or new_value == "":
                    continue
                old_value = getattr(family, column, None)
                if same_value(old_value, new_value):
                    continue
                by_officer = key in parsed.edited_fields
                _history(
                    session, "family", family.id, column, old_value, new_value,
                    batch, now, by_officer,
                )
                setattr(family, column, new_value)
                if column == "gps_coordinates":
                    family.location = point_from_gps(new_value)
                outcome.fields_changed += 1
                if by_officer:
                    outcome.fields_corrected += 1

            soldier = family.soldier
            if soldier is not None:
                for key, column in SOLDIER_FIELDS.items():
                    new_value = parsed.values.get(key)
                    if new_value is None or new_value == "":
                        continue
                    old_value = getattr(soldier, column, None)
                    if same_value(old_value, new_value):
                        continue
                    by_officer = key in parsed.edited_fields
                    _history(
                        session, "soldier", soldier.id, column, old_value, new_value,
                        batch, now, by_officer,
                    )
                    setattr(soldier, column, new_value)
                    outcome.fields_changed += 1
                    if by_officer:
                        outcome.fields_corrected += 1

            # Extra fields go into the pocket, and are recorded like any other
            # change â€” the never-overwrite rule applies to them too.
            if parsed.extra_fields:
                pocket = dict(family.extra_fields or {})
                for key, new_value in parsed.extra_fields.items():
                    if not new_value:
                        continue
                    old_value = pocket.get(key)
                    if same_value(old_value, new_value):
                        continue
                    _history(
                        session, "family", family.id, f"extra.{key}",
                        old_value, new_value, batch, now,
                    )
                    pocket[key] = new_value
                    outcome.fields_changed += 1
                    used_extra_keys.add(key)
                family.extra_fields = pocket

            outcome.fields_changed += _apply_children(
                session, family, parsed, batch, now
            )

            family.last_verified_on = date.today()
            outcome.updated += 1
            target_family_id = family.id

        # --- a family we have not seen before ---
        elif row_preview.action in (RowAction.create, RowAction.needs_decision):
            # Built in memory and saved with its group (see _save_group), so a
            # big sheet does not need several database trips per family.
            # Every mapped soldier and family field is copied across, so a
            # field added to the mapping is saved without touching this code.
            soldier = Soldier(
                full_name=parsed.values.get("soldier_name") or "Name not recorded"
            )
            for key, column in SOLDIER_FIELDS.items():
                value = parsed.values.get(key)
                if value not in (None, "") and key != "soldier_name":
                    setattr(soldier, column, value)
            # Older sheets give only one unit column; use it for both.
            if not soldier.regiment:
                soldier.regiment = soldier.unit

            code = next(codes)
            family = Family(
                family_code=code,
                soldier=soldier,
                primary_contact_name=parsed.values.get("widow_name")
                or soldier.full_name,
                extra_fields=dict(parsed.extra_fields),
                last_verified_on=date.today(),
            )
            for key, column in FAMILY_FIELDS.items():
                value = parsed.values.get(key)
                if value not in (None, "") and key != "widow_name":
                    setattr(family, column, value)
            family.location = point_from_gps(family.gps_coordinates)

            if parsed.values.get("widow_name"):
                relation = relation_from_text(family.nok_relationship)
                family.members.append(
                    FamilyMember(
                        full_name=parsed.values["widow_name"],
                        relation=relation,
                        gender="female" if relation in (Relation.widow, Relation.mother) else None,
                    )
                )
            # A family new to us has no children on record yet, so every child
            # in the row is a new record (as _apply_children would decide).
            children = [new_member(None, child) for child in sheet_children(parsed.values)]
            family.members.extend(children)
            session.add(family)

            outcome.created += 1
            outcome.new_family_codes.append(code)
            used_extra_keys.update(k for k, v in parsed.extra_fields.items() if v)
            if row_preview.action == RowAction.needs_decision:
                outcome.needs_decision += 1

            waiting.append(_NewFamily(
                family=family, code=code, children=children, row_number=row_number,
                row_preview=row_preview, problems=list(parsed.problems),
            ))
            if len(waiting) >= SAVE_GROUP_SIZE:
                _save_group(session, waiting, batch, now, outcome)
            continue
        else:
            continue

        _raise_row_problems(
            session, target_family_id, row_number, parsed.problems, batch, now, outcome
        )

    # The last group of new families.
    _save_group(session, waiting, batch, now, outcome)

    # Record which extra fields this sheet actually used.
    if used_extra_keys:
        for custom in session.scalars(
            select(CustomField).where(CustomField.key.in_(used_extra_keys))
        ).all():
            custom.times_used += 1
            custom.last_used_at = now

    session.add(
        AuditLog(
            user_id=batch.uploaded_by_user_id,
            action="import.commit",
            entity_type="import_batch",
            entity_id=batch.id,
            occurred_at=now,
            details={"filename": batch.original_filename, **outcome.as_dict()},
        )
    )

    return outcome
