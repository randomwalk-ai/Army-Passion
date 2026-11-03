"""Children Education Allowance (CEA): who can claim, and how much.

The numbers (age limits, how many children, monthly rates) are NOT written
here. They come from the scheme's `rules` JSON, which starts life in
`app/data/cea_scheme.json`. This file only knows how to read them, so a new
rate is a data change, not a code change.

What the circular says, in short:
- wards of every death-in-harness case can claim
- only the TWO ELDEST children, Class KG to 12, up to age 20
- from academic year 2017-18 onwards, claimed after the year ends
- a fixed amount per month; hostel subsidy on top; a divyang child gets double

Everything here is deterministic: same data in, same answer out. An officer
always looks at the result before anything is sent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Family, Scheme
from app.models.enums import Relation

DEFAULT_SCHEME_FILE = Path(__file__).resolve().parents[1] / "data" / "cea_scheme.json"
CHILD_RELATIONS = {Relation.son, Relation.daughter}

# Status words, the same ones the eligibility table uses.
ELIGIBLE = "eligible"
NOT_ELIGIBLE = "not_eligible"
ELIGIBLE_LATER = "eligible_later"
NEEDS_DATA = "needs_data"

# A class number that means "finished school" (college, ITI, diploma...).
BEYOND_SCHOOL = 13
NOT_STUDYING = -1


# --- the scheme row --------------------------------------------------------


def default_definition() -> dict[str, Any]:
    return json.loads(DEFAULT_SCHEME_FILE.read_text(encoding="utf-8"))


def ensure_cea_scheme(session: Session) -> Scheme:
    """The CEA scheme row, created from the JSON file the first time."""
    scheme = session.scalar(select(Scheme).where(Scheme.code == "CEA"))
    if scheme is not None:
        return scheme
    definition = default_definition()
    scheme = Scheme(**definition, is_mock=False, is_active=True)
    session.add(scheme)
    session.flush()
    return scheme


# --- academic years --------------------------------------------------------


@dataclass(frozen=True)
class AcademicYear:
    start_year: int
    start_month: int = 4

    @classmethod
    def parse(cls, label: str, start_month: int = 4) -> AcademicYear:
        """'2025-26' or '2025-2026' or '2025'."""
        match = re.match(r"^\s*(\d{4})", label or "")
        if not match:
            raise ValueError(f"Academic year should look like 2025-26, not {label!r}")
        return cls(int(match.group(1)), start_month)

    @classmethod
    def last_completed(cls, today: date, start_month: int = 4) -> AcademicYear:
        """Claims go in after the year ends, so this is the one to claim now."""
        started_this_year = today.month >= start_month
        current = today.year if started_this_year else today.year - 1
        return cls(current - 1, start_month)

    @property
    def label(self) -> str:
        return f"{self.start_year}-{str(self.start_year + 1)[-2:]}"

    @property
    def starts_on(self) -> date:
        return date(self.start_year, self.start_month, 1)

    @property
    def ends_on(self) -> date:
        """The last day before the next year starts."""
        month = self.start_month - 1 or 12
        year = self.start_year + 1 if self.start_month > 1 else self.start_year
        last_day = _days_in_month(year, month)
        return date(year, month, last_day)

    def months(self) -> list[date]:
        """The first day of each of the twelve months."""
        result = []
        year, month = self.start_year, self.start_month
        for _ in range(12):
            result.append(date(year, month, 1))
            month += 1
            if month == 13:
                year, month = year + 1, 1
        return result


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def age_on(dob: date, when: date) -> int:
    years = when.year - dob.year
    if (when.month, when.day) < (dob.month, dob.day):
        years -= 1
    return years


def birthday(dob: date, age: int) -> date:
    """The day someone born on `dob` turns `age` (29 Feb -> 1 Mar)."""
    try:
        return dob.replace(year=dob.year + age)
    except ValueError:
        return date(dob.year + age, 3, 1)


# --- reading a class ---------------------------------------------------------

ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}
PRE_SCHOOL = re.compile(r"\b(nursery|pre[\s-]?kg|lkg|ukg|kg|kindergarten|prep|play\s*school)\b")
AFTER_SCHOOL = re.compile(
    r"(graduat|college|universit|diploma|\biti\b|nursing|\bb\.?\s?(a|sc|com|tech|e|ed|ba|pharm)\b"
    r"|\bm\.?\s?(a|sc|com|tech|ba)\b|\byear\b|degree|polytechnic|mbbs|engineering)"
)


def class_number(text: str | None) -> int | None:
    """'Class 8' -> 8, 'XII' -> 12, 'UKG' -> 0, 'B.A. 1st year' -> 13.

    None means we could not tell. Written the many ways office sheets write it.
    """
    if not text:
        return None
    value = text.strip().lower()
    if not value:
        return None
    if "not studying" in value or value in {"none", "nil", "na", "n/a", "-"}:
        return NOT_STUDYING
    if AFTER_SCHOOL.search(value):
        return BEYOND_SCHOOL
    if PRE_SCHOOL.search(value):
        return 0
    words = re.sub(r"(class|std\.?|standard|grade|th|st|nd|rd)", " ", value).split()
    for word in words:
        word = word.strip(".-")
        if word.isdigit() and 1 <= int(word) <= 12:
            return int(word)
        if word in ROMAN:
            return ROMAN[word]
    return None


# --- the verdict -------------------------------------------------------------


@dataclass
class ChildInfo:
    """Just what the rules need, so tests can build children by hand."""

    member_id: int | None
    name: str
    dob: date | None
    is_studying: bool | None = None
    class_text: str | None = None
    has_disability: bool = False
    is_hostel: bool | None = None


@dataclass
class ChildVerdict:
    member_id: int | None
    name: str
    position: int | None  # 1 = eldest; None if we cannot tell
    status: str
    reasons: list[str] = field(default_factory=list)
    to_confirm: list[str] = field(default_factory=list)
    age: int | None = None
    class_number: int | None = None
    months: int = 0
    cea_amount: int = 0
    hostel_amount: int = 0
    becomes_eligible_on: date | None = None

    @property
    def total(self) -> int:
        return self.cea_amount + self.hostel_amount


@dataclass
class FamilyVerdict:
    status: str
    academic_year: str
    reasons: list[str] = field(default_factory=list)
    children: list[ChildVerdict] = field(default_factory=list)
    becomes_eligible_on: date | None = None

    @property
    def eligible_children(self) -> list[ChildVerdict]:
        return [c for c in self.children if c.status == ELIGIBLE]

    @property
    def total(self) -> int:
        return sum(c.total for c in self.eligible_children)


def _rate_for(month: date, rates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The rate row in force on the first of `month`, or None before the scheme."""
    current = None
    for rate in sorted(rates, key=lambda r: r["from"]):
        if date.fromisoformat(rate["from"]) <= month:
            current = rate
    return current


def _amounts(
    child: ChildInfo, year: AcademicYear, rules: dict[str, Any], date_of_death: date
) -> tuple[int, int, int]:
    """(months claimed, CEA amount, hostel amount) for one child for one year.

    Counted month by month, so a year that straddles a rate change, or the
    month the soldier died, comes out right.
    """
    first_month = date(date_of_death.year, date_of_death.month, 1)
    months = cea = hostel = 0
    for month in year.months():
        if month < first_month:
            continue
        rate = _rate_for(month, rules["rates"])
        if rate is None:
            continue
        months += 1
        cea += rate["divyang"] if child.has_disability else rate["cea"]
        if child.is_hostel:
            hostel += rate["hostel"]
    return months, cea, hostel


def evaluate(
    children: list[ChildInfo],
    date_of_death: date | None,
    year: AcademicYear,
    rules: dict[str, Any],
) -> FamilyVerdict:
    """The CEA verdict for one family for one academic year."""
    verdict = FamilyVerdict(status=NOT_ELIGIBLE, academic_year=year.label)

    if year.start_year < rules["first_academic_year"]:
        verdict.reasons.append(
            f"CEA for families of fallen soldiers starts from "
            f"{AcademicYear(rules['first_academic_year']).label}."
        )
        return verdict

    if date_of_death is None:
        verdict.status = NEEDS_DATA
        verdict.reasons.append("Soldier's date of death is not recorded.")
        return verdict

    if date_of_death > year.ends_on:
        verdict.reasons.append(
            f"The soldier died after {year.label} ended, so there is no claim for that year."
        )
        return verdict

    if not children:
        verdict.reasons.append("No children on record.")
        return verdict

    # The two eldest, by date of birth. A child with no date of birth cannot
    # be placed, so it is listed last and asked about.
    known = sorted((c for c in children if c.dob), key=lambda c: c.dob)  # type: ignore[arg-type,return-value]
    unknown = [c for c in children if not c.dob]
    limit = rules["eldest_children"]
    ordinal = {1: "eldest", 2: "second eldest"}

    for position, child in enumerate(known + unknown, start=1):
        result = ChildVerdict(
            member_id=child.member_id,
            name=child.name,
            position=position if child.dob else None,
            status=ELIGIBLE,
        )
        verdict.children.append(result)

        if child.dob is None:
            result.status = NEEDS_DATA
            result.reasons.append("Date of birth missing, so we cannot tell if this is one of the two eldest.")
            continue

        if position > limit:
            result.status = NOT_ELIGIBLE
            result.reasons.append(f"Only the {limit} eldest children can claim. This is child no. {position}.")
            continue

        result.age = age_on(child.dob, year.starts_on)
        result.class_number = class_number(child.class_text)

        if child.is_studying is False or result.class_number == NOT_STUDYING:
            result.status = NOT_ELIGIBLE
            result.reasons.append("Not studying.")
            continue

        if result.age > rules["max_age"]:
            result.status = NOT_ELIGIBLE
            result.reasons.append(
                f"Was {result.age} when {year.label} began. The limit is {rules['max_age']}."
            )
            continue

        if result.age < rules["min_age"]:
            result.status = ELIGIBLE_LATER
            result.becomes_eligible_on = birthday(child.dob, rules["min_age"])
            result.reasons.append(
                f"Too young for school in {year.label}. Can claim once in KG "
                f"(turns {rules['min_age']} on {result.becomes_eligible_on:%d-%m-%Y})."
            )
            continue

        if result.class_number is not None and result.class_number > rules["max_class"]:
            # A ten-year-old "in college" is a typing mistake, not a verdict.
            if result.age <= 16:
                result.status = NEEDS_DATA
                result.reasons.append(
                    f"Class is written as “{child.class_text}”, which does not fit age {result.age}. Please check."
                )
            else:
                result.status = NOT_ELIGIBLE
                result.reasons.append(
                    f"Studying “{child.class_text}” — beyond Class {rules['max_class']}."
                )
            continue

        # Class 1 is usually age 6. A class far ahead of (or behind) the age
        # is almost always a typing mistake; ask rather than pay or refuse.
        if result.class_number is not None and (
            result.class_number > result.age - 3 or result.class_number < result.age - 12
        ):
            result.status = NEEDS_DATA
            result.reasons.append(
                f"Class is written as “{child.class_text}”, which does not fit age {result.age}. Please check."
            )
            continue

        result.months, result.cea_amount, result.hostel_amount = _amounts(
            child, year, rules, date_of_death
        )
        if result.months == 0:
            result.status = NOT_ELIGIBLE
            result.reasons.append(f"No months of {year.label} fall after the date of death.")
            continue

        place = ordinal.get(position, f"child no. {position}")
        result.reasons.append(f"The {place} child, aged {result.age} when {year.label} began.")
        if result.class_number is None:
            result.to_confirm.append("Class not recorded — confirm the child is in KG to Class 12.")
        if child.is_hostel is None:
            result.to_confirm.append("Hostel not recorded — counted as day scholar.")
        if child.has_disability:
            result.reasons.append("Divyang child: double rate.")
        if result.months < 12:
            result.reasons.append(f"{result.months} of 12 months fall after the date of death.")

    # The family's verdict follows its best child.
    statuses = {c.status for c in verdict.children}
    if ELIGIBLE in statuses:
        verdict.status = ELIGIBLE
        count = len(verdict.eligible_children)
        verdict.reasons.append(f"{count} child{'ren' if count > 1 else ''} can claim for {year.label}.")
    elif NEEDS_DATA in statuses:
        verdict.status = NEEDS_DATA
        verdict.reasons.append("Some details are missing before we can decide.")
    elif ELIGIBLE_LATER in statuses:
        verdict.status = ELIGIBLE_LATER
        verdict.becomes_eligible_on = min(
            c.becomes_eligible_on for c in verdict.children if c.becomes_eligible_on
        )
        verdict.reasons.append("A child will be able to claim once in school.")
    else:
        verdict.reasons.append("No child can claim for this year.")
    return verdict


def children_of(family: Family) -> list[ChildInfo]:
    return [
        ChildInfo(
            member_id=m.id,
            name=m.full_name,
            dob=m.date_of_birth,
            is_studying=m.is_studying,
            # The CEA field wins; the general education level is a fallback.
            class_text=m.current_class or m.education_level,
            has_disability=bool(m.has_disability),
            is_hostel=m.is_hostel,
        )
        for m in family.members
        if m.relation in CHILD_RELATIONS
    ]


def evaluate_family(family: Family, year: AcademicYear, rules: dict[str, Any]) -> FamilyVerdict:
    soldier = family.soldier
    return evaluate(
        children_of(family),
        soldier.date_of_death if soldier else None,
        year,
        rules,
    )
