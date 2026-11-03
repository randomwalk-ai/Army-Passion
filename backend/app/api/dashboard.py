"""The numbers on the home screen.

Sent as a list of tiles rather than fixed fields, so adding a number here
shows up on the screen without changing the screen.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Application, DataQualityIssue, Document, Family, FamilyMember
from app.models.enums import ApplicationStage, IssueStatus, Relation
from app.services.cea import AcademicYear, ELIGIBLE, ensure_cea_scheme, evaluate_family

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class Stat(BaseModel):
    key: str
    label: str
    value: int
    hint: str | None = None
    # "attention" draws the eye; the rest stay quiet.
    tone: str = "normal"
    href: str | None = None


class DashboardResponse(BaseModel):
    stats: list[Stat]


@router.get("", response_model=DashboardResponse)
def dashboard(session: Session = Depends(get_session)) -> DashboardResponse:
    today = date.today()
    real = Family.is_draft.is_(False)

    families = session.scalar(select(func.count()).select_from(Family).where(real)) or 0
    people = session.scalar(
        select(func.count()).select_from(FamilyMember).join(Family).where(real)
    ) or 0
    applicants = session.scalar(
        select(func.count(distinct(Application.family_id)))
    ) or 0
    applications = session.scalar(select(func.count()).select_from(Application)) or 0

    open_stages = [
        s for s in ApplicationStage
        if s not in (ApplicationStage.money_credited, ApplicationStage.rejected)
    ]
    stuck = sum(
        1
        for a in session.scalars(
            select(Application).where(Application.stage.in_(open_stages))
        ).all()
        if a.is_stuck(today)
    )

    attention = session.scalar(
        select(func.count(distinct(DataQualityIssue.family_id))).where(
            DataQualityIssue.status == IssueStatus.open
        )
    ) or 0

    no_documents = session.scalar(
        select(func.count()).select_from(Family).where(
            real,
            ~select(Document.id)
            .where(Document.family_id == Family.id, Document.is_supporting.is_(True))
            .exists(),
        )
    ) or 0

    drafts = session.scalar(
        select(func.count()).select_from(Family).where(Family.is_draft.is_(True))
    ) or 0

    # 18th birthdays in the next 90 days: born between 18y+90d ago and 18y ago.
    soon = today + timedelta(days=90)
    turning_18 = session.scalar(
        select(func.count())
        .select_from(FamilyMember)
        .where(
            FamilyMember.relation.in_([Relation.son, Relation.daughter]),
            FamilyMember.date_of_birth > _years_before(today, 18),
            FamilyMember.date_of_birth <= _years_before(soon, 18),
        )
    ) or 0

    scheme = ensure_cea_scheme(session)
    session.commit()
    year = AcademicYear.last_completed(today, scheme.rules.get("academic_year_start_month", 4))
    cea_families = sum(
        1
        for f in session.scalars(
            select(Family).where(real).options(
                selectinload(Family.members), selectinload(Family.soldier)
            )
        ).all()
        if evaluate_family(f, year, scheme.rules).status == ELIGIBLE
    )

    stats = [
        Stat(key="families", label="Families", value=families,
             hint=f"{people:,} people in all"),
        Stat(key="applicants", label="Registered applicants", value=applicants,
             hint=f"{applications:,} applications in total"),
        Stat(key="cea", label="Can claim CEA", value=cea_families,
             hint=f"For {year.label}", href="/cea"),
        Stat(key="stuck", label="Applications stuck", value=stuck,
             hint="Waiting longer than they should",
             tone="attention" if stuck else "normal"),
        Stat(key="attention", label="Families with missing details", value=attention,
             hint="Phone, dates, bank details and so on",
             tone="attention" if attention else "normal"),
        Stat(key="no_documents", label="Families without documents", value=no_documents,
             hint="Each family needs 1 to 4", href="/families?filter=no_documents",
             tone="attention" if no_documents else "normal"),
        Stat(key="turning_18", label="Children turning 18 soon", value=turning_18,
             hint="In the next 3 months"),
    ]
    if drafts:
        stats.append(Stat(key="drafts", label="Unfinished families", value=drafts,
                          hint="Heard about in a voice note", tone="attention"))
    return DashboardResponse(stats=stats)


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)
