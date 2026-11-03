"""Finding a family, and adding one by hand."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user
from app.api.schemas import FamilySearchItem
from app.db import get_session
from app.models import Family
from app.services import family_create

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


class NewChildIn(BaseModel):
    name: str = ""
    sex: str = ""  # M / F
    date_of_birth: str = ""  # DD-MM-YYYY
    current_class: str = ""
    school_name: str = ""
    school_place: str = ""
    is_hostel: bool = False
    has_disability: bool = False


class FamilyCreateIn(BaseModel):
    # Keys are the same field keys an Excel column maps onto (soldier_name,
    # widow_name, phone, district...), so both routes share one set of rules.
    values: dict[str, str] = Field(default_factory=dict)
    children: list[NewChildIn] = Field(default_factory=list, max_length=10)
    # He has seen the "this looks like an existing family" warning and
    # still wants a new record.
    confirm_not_duplicate: bool = False


class FamilyCreatedOut(BaseModel):
    family_id: int
    family_code: str
    primary_contact_name: str
    warnings: list[str]


@router.post("", response_model=FamilyCreatedOut, status_code=201)
def create_family(
    body: FamilyCreateIn, session: Session = Depends(get_session)
) -> FamilyCreatedOut:
    """One family, typed in on the form.

    422: something is typed wrongly (with a message per field).
    409: it looks like a family we already have; he decides.
    """
    try:
        checked = family_create.check(
            body.values, [family_create.NewChild(**c.model_dump()) for c in body.children]
        )
    except family_create.FormErrors as e:
        raise HTTPException(422, {"message": "Please check the highlighted boxes.", "errors": e.errors}) from e

    if not body.confirm_not_duplicate:
        matches = family_create.possible_duplicates(session, checked.parsed)
        if matches:
            families = {
                f.id: f
                for f in session.scalars(
                    select(Family)
                    .where(Family.id.in_([m.family_id for m in matches]))
                    .options(selectinload(Family.soldier))
                ).all()
            }
            raise HTTPException(
                409,
                {
                    "message": "This looks like a family that is already in the system.",
                    "matches": [
                        {
                            **asdict(m),
                            "primary_contact_name": families[m.family_id].primary_contact_name,
                            "soldier_name": families[m.family_id].soldier.full_name
                            if families[m.family_id].soldier
                            else None,
                            "district": families[m.family_id].district,
                        }
                        for m in matches
                    ],
                },
            )

    user = current_user(session)
    family = family_create.create(session, checked, user.id if user else None)
    session.commit()
    return FamilyCreatedOut(
        family_id=family.id,
        family_code=family.family_code,
        primary_contact_name=family.primary_contact_name,
        warnings=checked.warnings,
    )
