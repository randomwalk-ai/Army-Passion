"""Two things the chatbot cannot answer with a plain database search:

- **CEA eligibility** is not a stored column; it comes from our own rule
  engine (`app/services/cea.py`), the same one the CEA screen uses.
- **One named family's full details** (its members, soldier, applications)
  are easier and safer to assemble in Python than in one SQL query, and the
  name typed by the colonel may be misspelled or incomplete.

Both are "tools" the chatbot can choose, the same idea as a database search,
but run by our own code instead of the LLM's SQL. The LLM only ever sends a
year or a name — never sees the rows that come back.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Family, Soldier
from app.services.ask import Answer, _cell, error
from app.services.cea import (
    ELIGIBLE,
    ELIGIBLE_LATER,
    NEEDS_DATA,
    NOT_ELIGIBLE,
    AcademicYear,
    ensure_cea_scheme,
    evaluate_family,
)

MAX_CANDIDATES = 8


STATUS_WORDS = {
    ELIGIBLE: "Eligible",
    NOT_ELIGIBLE: "Not eligible",
    ELIGIBLE_LATER: "Eligible later",
    NEEDS_DATA: "Details missing",
}


def cea_tool(
    session: Session, year_label: str | None, today: date, name: str | None = None
) -> Answer:
    """CEA in one academic year, using the real CEA rules.

    With a `name`, checks that one family child by child ("is Meena Dagar
    eligible?"); without, lists every child who can claim.
    """
    scheme = ensure_cea_scheme(session)
    session.commit()
    start_month = scheme.rules.get("academic_year_start_month", 4)
    note = ""
    try:
        year = AcademicYear.parse(year_label, start_month) if year_label else None
    except ValueError:
        year = None
    if year is None:
        year = AcademicYear.last_completed(today, start_month)
        if year_label:
            note = f" (I could not read “{year_label}” as a year, so I used {year.label})"

    if name and name.strip():
        return _cea_for_family(session, name.strip(), year, scheme.rules, note)

    families = session.scalars(
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
        .order_by(Family.primary_contact_name)
    ).all()

    rows: list[list[object]] = []
    for family in families:
        verdict = evaluate_family(family, year, scheme.rules)
        if verdict.status != ELIGIBLE:
            continue
        for child in verdict.eligible_children:
            rows.append([
                family.family_code,
                family.primary_contact_name,
                family.district,
                child.name,
                child.age,
                f"Class {child.class_number}" if child.class_number else None,
                child.cea_amount + child.hostel_amount,
            ])

    return Answer(
        kind="table",
        title=f"Children eligible for CEA, academic year {year.label}{note}",
        tool=f"cea for all families, year {year.label}",
        columns=["Family Code", "Widow / NOK", "District", "Child", "Age", "Class",
                 "Monthly amount (₹)"],
        rows=rows,
        count=len(rows),
    )


def _cea_for_family(
    session: Session, name: str, year: AcademicYear, rules: dict, note: str
) -> Answer:
    matches = _candidates(session, name)
    if not matches:
        return _not_found(
            session,
            name,
            "Is {code} ({who}) eligible for CEA in " + year.label + "?",
            f"cea for one family named {name!r}, year {year.label} (not found)",
        )
    if len(matches) > 1:
        return Answer(
            kind="clarify",
            message=f"{len(matches)} families match “{name}”. Which one?",
            options=[
                f"Is {f.family_code} ({f.primary_contact_name}, {f.district}) eligible for CEA in {year.label}?"
                for f in matches[:MAX_CANDIDATES]
            ],
            tool=f"cea for one family named {name!r}, year {year.label} (several matched)",
        )

    family = matches[0]
    verdict = evaluate_family(family, year, rules)
    who = f"{family.primary_contact_name}'s family ({family.family_code}, {family.district})"
    tool = f"cea for family {family.family_code} ({family.primary_contact_name}), year {year.label}"
    if not verdict.children:
        reason = " ".join(verdict.reasons) or "No children on record."
        return Answer(
            kind="message",
            message=f"{who}: not eligible for CEA in {year.label}{note}. {reason}",
            tool=tool,
        )

    eligible = len(verdict.eligible_children)
    rows = [[
        child.name,
        child.age,
        STATUS_WORDS.get(child.status, child.status),
        " ".join(child.reasons) or ("Can claim." if child.status == ELIGIBLE else None),
        child.total if child.status == ELIGIBLE else None,
        family.family_code,
    ] for child in verdict.children]
    verb = "is" if eligible == 1 else "are"
    return Answer(
        kind="table",
        title=(
            f"CEA {year.label} for {who}{note}: {eligible} of {len(verdict.children)} "
            f"children {verb} eligible"
        ),
        columns=["Child", "Age", "CEA", "Why", "Amount for the year (₹)", "Family code"],
        rows=rows,
        count=len(rows),
        tool=tool,
    )


def _candidates(session: Session, name: str) -> list[Family]:
    """Families whose widow/NOK, soldier, or family code loosely matches `name`.

    Matches on every word typed (so "paramjit moga" needs both to appear
    somewhere), not an exact match, so a misspelling or a partial name still
    finds the family.
    """
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if not words:
        return []
    query = (
        select(Family)
        .join(Soldier, Family.soldier_id == Soldier.id)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
    )
    for word in words:
        like = f"%{word}%"
        query = query.where(
            or_(
                Family.primary_contact_name.ilike(like),
                Family.family_code.ilike(like),
                Soldier.full_name.ilike(like),
            )
        )
    return list(session.scalars(query.order_by(Family.primary_contact_name)).unique())


def _near_matches(session: Session, name: str) -> list[Family]:
    """Families matching ANY word of `name` (not all), for "did you mean...?"."""
    words = [w for w in re.split(r"\s+", name.strip()) if len(w) >= 3]
    if not words:
        return []
    conditions = []
    for word in words:
        like = f"%{word}%"
        conditions += [Family.primary_contact_name.ilike(like), Soldier.full_name.ilike(like)]
    query = (
        select(Family)
        .join(Soldier, Family.soldier_id == Soldier.id)
        .where(Family.is_draft.is_(False), or_(*conditions))
        .order_by(Family.primary_contact_name)
        .limit(MAX_CANDIDATES)
    )
    return list(session.scalars(query).unique())


def _not_found(session: Session, name: str, ask: str, tool: str) -> Answer:
    """No family has every word of the name: offer the ones that have some.

    `ask` is the question each choice asks when clicked, with {code} and {who}.
    """
    near = _near_matches(session, name)
    if not near:
        return Answer(
            kind="message", message=f"I could not find a family matching “{name}”.", tool=tool
        )
    return Answer(
        kind="clarify",
        message=f"I could not find “{name}”. Did you mean one of these?",
        options=[
            ask.format(code=f.family_code, who=f"{f.primary_contact_name}, {f.district}")
            for f in near
        ],
        tool=tool,
    )


def family_tool(session: Session, name: str, today: date) -> Answer:
    """One family's roster: the widow, children, and how to reach them."""
    name = (name or "").strip()
    if not name:
        return error("Tell me which family — a name, or a family code like AP-2026-0006.")

    matches = _candidates(session, name)
    if not matches:
        return _not_found(
            session, name, "Details of {code} ({who})", f"family details for {name!r} (not found)"
        )

    if len(matches) > 1:
        options = [
            f"{f.family_code} — {f.primary_contact_name} ({f.district})" for f in matches[:MAX_CANDIDATES]
        ]
        more = "" if len(matches) <= MAX_CANDIDATES else f" and {len(matches) - MAX_CANDIDATES} more"
        return Answer(
            kind="clarify",
            message=f"{len(matches)} families match “{name}”{more}. Which one?",
            options=options,
        )

    family = matches[0]
    rows = [[
        member.full_name,
        member.relation.value,
        _cell(member.date_of_birth),
        family.primary_phone,
        family.district,
        family.last_contacted_on and _cell(family.last_contacted_on),
        family.family_code,
    ] for member in sorted(
        family.members, key=lambda m: (m.relation.value != "widow", m.date_of_birth or date.min)
    )]
    return Answer(
        kind="table",
        title=f"{family.primary_contact_name}'s family ({family.family_code}, {family.district})",
        tool=f"family details for {family.family_code} ({family.primary_contact_name})",
        columns=["Name", "Relation", "Date of birth", "Phone", "District", "Last contacted",
                 "Family code"],
        rows=rows,
        count=len(rows),
    )
