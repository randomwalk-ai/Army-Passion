"""Adding one family by hand, from the "Add a family" form.

The typed values go through the same cleaners as an Excel row, so a date or
phone number typed here is stored exactly as one from a sheet would be. The
only difference is the source in the history: an officer, not a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import AuditLog, DataQualityIssue, Family, FamilyMember, FieldHistory, Soldier
from app.models.enums import ChangeSource, IssueCode, IssueStatus, Relation
from app.services.column_mapping import TARGET_BY_KEY
from app.services.import_apply import next_family_code, point_from_gps, relation_from_text
from app.services.import_preview import FAMILY_FIELDS, SOLDIER_FIELDS
from app.services.matching import Candidate, FamilyIndex
from app.services.row_parser import ParsedRow, parse_date, parse_row, parse_sex, tidy_name

IST = ZoneInfo("Asia/Kolkata")
SOURCE_REFERENCE = "Added by hand"

# Absent rather than wrong: worth a reminder later, not worth blocking him now.
MISSING_ONLY = {IssueCode.missing_phone, IssueCode.missing_date_of_death}


@dataclass
class NewChild:
    name: str
    sex: str = ""
    date_of_birth: str = ""
    current_class: str = ""
    school_name: str = ""
    school_place: str = ""
    is_hostel: bool = False
    has_disability: bool = False


class FormErrors(ValueError):
    """Values that cannot be stored as typed, keyed by form field."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


@dataclass
class Checked:
    parsed: ParsedRow
    children: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(values: dict[str, str], children: list[NewChild]) -> Checked:
    """Clean and validate everything. Raises FormErrors if anything is wrong."""
    known = {k: (v or "") for k, v in values.items() if k in TARGET_BY_KEY and not k.startswith("child")}
    headers = list(known)
    parsed = parse_row([known[h] for h in headers], {h: h for h in headers}, headers, 0)

    errors: dict[str, str] = {}
    warnings: list[str] = []
    for problem in parsed.problems:
        if problem.code in MISSING_ONLY:
            warnings.append(problem.message.replace(" in this row", ""))
        else:
            label = TARGET_BY_KEY[problem.field_name].label
            errors[problem.field_name] = f"{label}: {problem.message}"

    if not parsed.values.get("soldier_name"):
        errors["soldier_name"] = "Please type the soldier's name."
    if not parsed.values.get("widow_name"):
        errors["widow_name"] = "Please type the name of the next of kin."

    cleaned_children = []
    for index, child in enumerate(children):
        name = tidy_name(child.name)
        if not name:
            # An empty child row is just an unused row on the form.
            if any([child.date_of_birth, child.school_name, child.current_class]):
                errors[f"children.{index}.name"] = f"Child {index + 1}: please type the name."
            continue
        dob, problem = parse_date(child.date_of_birth)
        if problem:
            errors[f"children.{index}.date_of_birth"] = f"{name}: {problem}"
        sex, problem = parse_sex(child.sex)
        if problem:
            errors[f"children.{index}.sex"] = f"{name}: {problem}"
        cleaned_children.append(
            {
                "full_name": name,
                "relation": Relation.son if sex == "male" else Relation.daughter if sex == "female" else Relation.other_dependent,
                "gender": sex,
                "date_of_birth": dob,
                "current_class": child.current_class.strip() or None,
                "school_name": child.school_name.strip() or None,
                "school_place": child.school_place.strip() or None,
                "is_hostel": child.is_hostel,
                "has_disability": child.has_disability,
                "is_studying": True if child.current_class.strip() or child.school_name.strip() else None,
            }
        )

    if errors:
        raise FormErrors(errors)
    return Checked(parsed=parsed, children=cleaned_children, warnings=warnings)


def possible_duplicates(session: Session, parsed: ParsedRow) -> list[Candidate]:
    """Families that look like the one being typed in. Never merges anything."""
    result = FamilyIndex(session).find(parsed)
    candidates = [c for c in [result.best, *result.others] if c and c.score >= 40]
    return candidates


def create(session: Session, checked: Checked, user_id: int | None) -> Family:
    parsed = checked.parsed
    now = datetime.now(IST)

    soldier = Soldier(full_name=parsed.values["soldier_name"])
    for key, column in SOLDIER_FIELDS.items():
        value = parsed.values.get(key)
        if value not in (None, "") and key != "soldier_name":
            setattr(soldier, column, value)
    if not soldier.regiment:
        soldier.regiment = soldier.unit
    session.add(soldier)
    session.flush()

    code = next_family_code(session)
    family = Family(
        family_code=code,
        soldier_id=soldier.id,
        primary_contact_name=parsed.values["widow_name"],
        extra_fields={},
        last_verified_on=now.date(),
    )
    for key, column in FAMILY_FIELDS.items():
        value = parsed.values.get(key)
        if value not in (None, "") and key != "widow_name":
            setattr(family, column, value)
    family.location = point_from_gps(family.gps_coordinates)
    session.add(family)
    session.flush()

    relation = relation_from_text(family.nok_relationship)
    session.add(
        FamilyMember(
            family_id=family.id,
            full_name=family.primary_contact_name,
            relation=relation,
            gender="female" if relation in (Relation.widow, Relation.mother) else None,
        )
    )
    for child in checked.children:
        session.add(FamilyMember(family_id=family.id, **child))
    session.flush()

    session.add(
        FieldHistory(
            entity_type="family",
            entity_id=family.id,
            field_name="__created__",
            old_value=None,
            new_value=code,
            source=ChangeSource.officer_entry,
            source_reference=SOURCE_REFERENCE,
            changed_at=now,
            changed_by_user_id=user_id,
        )
    )

    # What he left blank goes on the "needs attention" list, not into a void.
    for problem in parsed.problems:
        if problem.code in MISSING_ONLY:
            session.add(
                DataQualityIssue(
                    entity_type="family",
                    entity_id=family.id,
                    family_id=family.id,
                    issue_code=problem.code,
                    severity=problem.severity,
                    status=IssueStatus.open,
                    field_name=problem.field_name,
                    description=problem.message.replace("in this row", "for this family"),
                    details={"source": SOURCE_REFERENCE},
                    detected_at=now,
                )
            )

    session.add(
        AuditLog(
            user_id=user_id,
            action="family.create",
            entity_type="family",
            entity_id=family.id,
            occurred_at=now,
            details={"family_code": code, "children": len(checked.children)},
        )
    )
    return family
