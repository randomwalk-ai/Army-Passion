"""Children, as the colonel's sheet lays them out: side by side in one row.

His sheet has Name_of_Child1, Sex_Child1, DOB_Child1, Marital_Status_Child1,
then the same for Child2 and Child3. We store each child as its own record.

On an update, each child in the sheet is matched to a child already on
record, so re-importing the same sheet never adds the same child twice.
A child missing from the sheet is never deleted — a blank means "no
information", not "remove".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.models import FamilyMember
from app.models.enums import Relation
from app.services.matching import simplify

CHILD_SLOTS = (1, 2, 3)
CHILD_RELATIONS = (Relation.son, Relation.daughter, Relation.other_dependent)


@dataclass
class SheetChild:
    slot: int
    name: str
    sex: str | None  # "male" / "female"
    dob: date | None
    marital_status: str | None

    @property
    def relation(self) -> Relation:
        if self.sex == "male":
            return Relation.son
        if self.sex == "female":
            return Relation.daughter
        return Relation.other_dependent  # sex not given in the sheet

    @property
    def is_married(self) -> bool | None:
        if not self.marital_status:
            return None
        value = self.marital_status.strip().lower()
        if value.startswith("un") or value in {"single", "no"}:
            return False
        if value.startswith("married") or value in {"yes", "widowed", "divorced"}:
            return True
        return None


def sheet_children(values: dict[str, object]) -> list[SheetChild]:
    """The children in one parsed row. A slot with no name is skipped."""
    found: list[SheetChild] = []
    for slot in CHILD_SLOTS:
        name = values.get(f"child{slot}_name")
        if not name:
            continue
        dob = values.get(f"child{slot}_dob")
        found.append(
            SheetChild(
                slot=slot,
                name=str(name),
                sex=values.get(f"child{slot}_sex"),  # type: ignore[arg-type]
                dob=dob if isinstance(dob, date) else None,
                marital_status=values.get(f"child{slot}_marital_status"),  # type: ignore[arg-type]
            )
        )
    return found


def _first_name(name: str | None) -> str:
    parts = simplify(name).split()
    return parts[0] if parts else ""


def match_child(
    child: SheetChild, members: list[FamilyMember], taken: set[int]
) -> FamilyMember | None:
    """Find the same child already on record.

    Same full name first, then same date of birth, then same first name.
    `taken` stops two sheet children matching one record.
    """
    candidates = [
        m for m in members if m.relation in CHILD_RELATIONS and m.id not in taken
    ]
    for member in candidates:
        if simplify(member.full_name) == simplify(child.name):
            return member
    if child.dob:
        for member in candidates:
            if member.date_of_birth == child.dob:
                return member
    first = _first_name(child.name)
    if first:
        for member in candidates:
            if _first_name(member.full_name) == first:
                return member
    return None


def child_differences(
    child: SheetChild, member: FamilyMember
) -> list[tuple[str, str, object, object]]:
    """(column, label part, old, new) for what the sheet would change.

    Only values the sheet actually gives are compared; blanks never wipe.
    """
    from app.services.import_preview import same_value

    proposed = [
        ("full_name", "name", member.full_name, child.name),
        ("date_of_birth", "date of birth", member.date_of_birth, child.dob),
        ("gender", "sex", member.gender, child.sex),
        ("marital_status", "marital status", member.marital_status, child.marital_status),
    ]
    return [
        (column, label, old, new)
        for column, label, old, new in proposed
        if new not in (None, "") and not same_value(old, new)
    ]


def new_member(family_id: int, child: SheetChild) -> FamilyMember:
    return FamilyMember(
        family_id=family_id,
        full_name=child.name,
        relation=child.relation,
        date_of_birth=child.dob,
        gender=child.sex,
        marital_status=child.marital_status,
        is_married=child.is_married,
    )
