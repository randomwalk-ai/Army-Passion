"""Every scheme a family can be checked against, in one list.

Each scheme plugs in here with the same shape: a name, a short description,
the period it is checked for, and a function that gives every family one of
four answers:

    eligible        can claim now
    needs_data      might be able to, but a detail is missing
    eligible_later  not yet (e.g. a child too young), but will be
    not_eligible    cannot claim

The screens only read this list, so adding a scheme here makes it appear on
the Eligibility page, in the families table and in each family's panel,
without touching the frontend.

To add a scheme: write a `check(session, families) -> {family_id: Verdict}`
(its rules belong in data, like app/data/cea_scheme.json), then append a
`Scheme(...)` to SCHEMES below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Family
from app.services import cea

ELIGIBLE = cea.ELIGIBLE
NEEDS_DATA = cea.NEEDS_DATA
ELIGIBLE_LATER = cea.ELIGIBLE_LATER
NOT_ELIGIBLE = cea.NOT_ELIGIBLE
STATUSES = (ELIGIBLE, NEEDS_DATA, ELIGIBLE_LATER, NOT_ELIGIBLE)


@dataclass
class Verdict:
    status: str
    # One sentence for the table and the family panel.
    headline: str
    reasons: list[str] = field(default_factory=list)
    amount: int = 0


@dataclass(frozen=True)
class Scheme:
    code: str
    name: str
    short_name: str  # for a narrow table column
    description: str
    # Where the officer acts on it (fills the claim and so on).
    href: str
    status_labels: dict[str, str]
    period: Callable[[Session], str]
    check: Callable[[Session, list[Family]], dict[int, Verdict]]
    family_href: Callable[[int], str] | None = None


# --- CEA ------------------------------------------------------------------------


def _cea_year(session: Session) -> tuple[cea.AcademicYear, dict]:
    rules = cea.ensure_cea_scheme(session).rules
    year = cea.AcademicYear.last_completed(date.today(), rules.get("academic_year_start_month", 4))
    return year, rules


def _first(name: str) -> str:
    return name.split()[0] if name else "Child"


def _cea_check(session: Session, families: list[Family]) -> dict[int, Verdict]:
    year, rules = _cea_year(session)
    out: dict[int, Verdict] = {}
    for family in families:
        v = cea.evaluate_family(family, year, rules)
        child_reasons = [f"{_first(c.name)}: {' '.join(c.reasons)}" for c in v.children if c.reasons]
        reasons = [*v.reasons, *child_reasons]
        if v.status == ELIGIBLE:
            names = " and ".join(_first(c.name) for c in v.eligible_children)
            headline = f"{names} can claim for {year.label}"
        elif v.status == NEEDS_DATA:
            stuck = next((c for c in v.children if c.status == NEEDS_DATA and c.reasons), None)
            headline = f"{_first(stuck.name)}: {stuck.reasons[0]}" if stuck else (v.reasons or ["A detail is missing"])[0]
        elif v.status == ELIGIBLE_LATER and v.becomes_eligible_on:
            headline = f"Can claim from {v.becomes_eligible_on.strftime('%d-%m-%Y')}"
        else:
            headline = (reasons or ["No child can claim"])[0]
        out[family.id] = Verdict(v.status, headline, reasons, v.total)
    return out


CEA = Scheme(
    code="CEA",
    name="Children Education Allowance",
    short_name="CEA",
    description="School fees for the two eldest children, KG to Class 12, up to age 20. Paid yearly after the academic year ends.",
    href="/cea",
    status_labels={
        ELIGIBLE: "Can claim",
        NEEDS_DATA: "Details missing",
        ELIGIBLE_LATER: "Can claim later",
        NOT_ELIGIBLE: "Cannot claim",
    },
    period=lambda session: f"Academic year {_cea_year(session)[0].label}",
    check=_cea_check,
    family_href=lambda family_id: f"/cea/{family_id}",
)


# The order here is the order on screen.
SCHEMES: list[Scheme] = [CEA]


def by_code(code: str) -> Scheme | None:
    return next((s for s in SCHEMES if s.code == code), None)


def load_families(session: Session, family_ids: list[int] | None = None) -> list[Family]:
    """Real (non-draft) families with what the checks need already loaded."""
    statement = (
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
        .order_by(Family.id)
    )
    if family_ids is not None:
        statement = statement.where(Family.id.in_(family_ids))
    return list(session.scalars(statement).all())


def check_all(session: Session, families: list[Family]) -> dict[str, dict[int, Verdict]]:
    """{scheme code: {family id: verdict}} for every scheme."""
    return {s.code: s.check(session, families) for s in SCHEMES}
