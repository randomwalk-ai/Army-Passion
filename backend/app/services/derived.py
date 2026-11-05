"""Keeps child_facts and cea_by_year up to date for the chatbot.

They hold what our own code works out (CEA eligibility from the real rules in
cea.py, and each child's class as a number) so a chatbot search can filter on
them like any other column.

They are rebuilt only when the data has changed: a fingerprint of the
families, members and soldiers (how many, and when last changed) plus today's
date (ages move on daily) is compared with the one saved last time. Asking a
question when nothing changed costs one small query.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import CeaByYear, ChildFacts, DerivedState, Family
from app.services.cea import (
    CHILD_RELATIONS,
    ELIGIBLE,
    ELIGIBLE_LATER,
    NEEDS_DATA,
    NOT_ELIGIBLE,
    AcademicYear,
    class_number,
    ensure_cea_scheme,
    evaluate_family,
)

STATE_NAME = "child_facts"
# Years either side of the claimable year, so "eligible by 2028" can be asked.
YEARS_BEFORE = 1
YEARS_AFTER = 3
INSERT_CHUNK = 1000

STATUS_WORDS = {
    ELIGIBLE: "eligible",
    NOT_ELIGIBLE: "not eligible",
    ELIGIBLE_LATER: "eligible later",
    NEEDS_DATA: "details missing",
}

_FINGERPRINT = text(
    """
    SELECT concat_ws('|',
        (SELECT count(*) FROM families),
        (SELECT max(updated_at) FROM families),
        (SELECT count(*) FROM family_members),
        (SELECT max(updated_at) FROM family_members),
        (SELECT count(*) FROM soldiers),
        (SELECT max(updated_at) FROM soldiers),
        current_date)
    """
)


def current_fingerprint(session: Session) -> str:
    return session.execute(_FINGERPRINT).scalar_one()


def is_fresh(session: Session) -> bool:
    saved = session.get(DerivedState, STATE_NAME)
    return saved is not None and saved.fingerprint == current_fingerprint(session)


def refresh(session: Session, today: date | None = None) -> int:
    """Rebuild both tables from the real data. Returns how many children were done."""
    today = today or date.today()
    scheme = ensure_cea_scheme(session)
    rules = scheme.rules
    start_month = rules.get("academic_year_start_month", 4)
    claimable = AcademicYear.last_completed(today, start_month)
    years = [
        AcademicYear(claimable.start_year + offset, start_month)
        for offset in range(-YEARS_BEFORE, YEARS_AFTER + 1)
    ]

    families = session.scalars(
        select(Family).options(selectinload(Family.members), selectinload(Family.soldier))
    ).all()

    facts: list[dict] = []
    by_year: list[dict] = []
    for family in families:
        children = [m for m in family.members if m.relation in CHILD_RELATIONS]
        if not children:
            continue
        numbers = {m.id: class_number(m.current_class or m.education_level) for m in children}
        for year in years:
            verdict = evaluate_family(family, year, rules)
            per_child = {c.member_id: c for c in verdict.children}
            for member in children:
                child = per_child.get(member.id)
                if child is None:
                    # The family as a whole cannot claim (e.g. the soldier died
                    # after this year): the family's reason applies to each child.
                    status = STATUS_WORDS.get(verdict.status, verdict.status)
                    reason = " ".join(verdict.reasons) or None
                    amount, age = None, None
                else:
                    status = STATUS_WORDS.get(child.status, child.status)
                    reason = " ".join(child.reasons) or ("Can claim." if child.status == ELIGIBLE else None)
                    amount = child.total if child.status == ELIGIBLE else None
                    age = child.age
                by_year.append({
                    "member_id": member.id, "academic_year": year.label, "status": status,
                    "reason": reason, "amount": amount, "age_at_start": age,
                    "class_number": numbers[member.id],
                })
                if year == claimable:
                    facts.append({
                        "member_id": member.id, "class_number": numbers[member.id],
                        "cea_year": year.label, "cea_status": status,
                        "cea_reason": reason, "cea_amount": amount,
                    })

    session.execute(delete(CeaByYear))
    session.execute(delete(ChildFacts))
    # One multi-row INSERT per chunk: a trip to the database per 1,000 rows,
    # not per row (that made a rebuild take seconds, and far longer on Render).
    for table, rows in ((ChildFacts.__table__, facts), (CeaByYear.__table__, by_year)):
        for start in range(0, len(rows), INSERT_CHUNK):
            session.execute(insert(table).values(rows[start : start + INSERT_CHUNK]))

    fingerprint = current_fingerprint(session)
    saved = session.get(DerivedState, STATE_NAME)
    now = datetime.now(timezone.utc)
    if saved is None:
        session.add(DerivedState(name=STATE_NAME, fingerprint=fingerprint, refreshed_at=now))
    else:
        saved.fingerprint, saved.refreshed_at = fingerprint, now
    session.flush()
    return len(facts)


def ensure_fresh(session: Session) -> bool:
    """Rebuild if the data changed since last time. Returns whether it rebuilt.

    Two people asking at the same moment on a stale database would otherwise
    both rebuild; a transaction-level lock makes the second one wait, then see
    the fresh fingerprint and do nothing.
    """
    if is_fresh(session):
        return False
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext('child_facts'))"))
    if is_fresh(session):
        return False
    refresh(session)
    return True
