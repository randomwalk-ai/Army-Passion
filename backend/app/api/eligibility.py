"""Eligibility across every scheme: the overview, and one family's answers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import eligibility
from app.services.eligibility import ELIGIBLE, STATUSES

router = APIRouter(tags=["eligibility"])


class StatusCount(BaseModel):
    status: str
    label: str
    count: int


class SchemeOverview(BaseModel):
    code: str
    name: str
    description: str
    period: str
    href: str
    families_checked: int
    counts: list[StatusCount]
    # What the families who can claim now would receive in all.
    amount_total: int


class OverviewOut(BaseModel):
    schemes: list[SchemeOverview]


class FamilySchemeOut(BaseModel):
    code: str
    name: str
    period: str
    status: str
    label: str
    headline: str
    reasons: list[str]
    amount: int
    href: str | None


@router.get("/api/eligibility", response_model=OverviewOut)
def overview(session: Session = Depends(get_session)) -> OverviewOut:
    """How many families fall under each answer, for every scheme."""
    families = eligibility.load_families(session)
    out = []
    for scheme in eligibility.SCHEMES:
        verdicts = scheme.check(session, families).values()
        out.append(
            SchemeOverview(
                code=scheme.code,
                name=scheme.name,
                description=scheme.description,
                period=scheme.period(session),
                href=scheme.href,
                families_checked=len(families),
                counts=[
                    StatusCount(
                        status=status,
                        label=scheme.status_labels[status],
                        count=sum(1 for v in verdicts if v.status == status),
                    )
                    for status in STATUSES
                ],
                amount_total=sum(v.amount for v in verdicts if v.status == ELIGIBLE),
            )
        )
    session.commit()  # ensure_cea_scheme may have created the scheme row
    return OverviewOut(schemes=out)


@router.get("/api/families/{family_id}/eligibility", response_model=list[FamilySchemeOut])
def for_family(family_id: int, session: Session = Depends(get_session)) -> list[FamilySchemeOut]:
    """Every scheme's answer for one family, with the reasons."""
    families = eligibility.load_families(session, [family_id])
    if not families:
        raise HTTPException(404, "That family was not found.")
    family = families[0]
    out = []
    for scheme in eligibility.SCHEMES:
        verdict = scheme.check(session, families)[family.id]
        out.append(
            FamilySchemeOut(
                code=scheme.code,
                name=scheme.name,
                period=scheme.period(session),
                status=verdict.status,
                label=scheme.status_labels[verdict.status],
                headline=verdict.headline,
                reasons=verdict.reasons,
                amount=verdict.amount,
                href=scheme.family_href(family.id) if scheme.family_href else None,
            )
        )
    return out
