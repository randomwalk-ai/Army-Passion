"""Finding a family. Used by the voice-note picker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import FamilySearchItem
from app.db import get_session
from app.models import Family

router = APIRouter(prefix="/api/families", tags=["families"])


@router.get("/search", response_model=list[FamilySearchItem])
def search_families(
    q: str = Query("", description="Name, family code, district or phone"),
    include_drafts: bool = True,
    limit: int = Query(15, le=50),
    session: Session = Depends(get_session),
) -> list[FamilySearchItem]:
    """Search by whatever he happens to remember about the family."""
    statement = select(Family).options(selectinload(Family.soldier))

    if not include_drafts:
        statement = statement.where(Family.is_draft.is_(False))

    term = q.strip()
    if term:
        like = f"%{term}%"
        statement = statement.where(
            or_(
                Family.primary_contact_name.ilike(like),
                Family.family_code.ilike(like),
                Family.district.ilike(like),
                Family.primary_phone.ilike(like),
            )
        )

    # Drafts first: they are the ones still needing work.
    statement = statement.order_by(
        Family.is_draft.desc(), Family.primary_contact_name
    ).limit(limit)

    return [
        FamilySearchItem(
            family_id=family.id,
            family_code=family.family_code,
            primary_contact_name=family.primary_contact_name,
            soldier_name=family.soldier.full_name if family.soldier else None,
            district=family.district,
            state=family.state,
            is_draft=family.is_draft,
        )
        for family in session.scalars(statement).all()
    ]
