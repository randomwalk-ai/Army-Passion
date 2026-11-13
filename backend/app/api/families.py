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
from app.services import family_create, family_table

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


# --- the families table -----------------------------------------------------------


class TableColumnOut(BaseModel):
    key: str
    label: str
    kind: str
    editable: bool
    sortable: bool
    required: bool
    choices: list[str]
    # The heading it sits under in the family panel.
    group: str


class SchemeVerdictOut(BaseModel):
    status: str
    label: str
    headline: str
    amount: int


class TableRowOut(BaseModel):
    family_id: int
    values: dict[str, str | int | None]
    # One verdict per scheme, keyed by scheme code ("CEA").
    eligibility: dict[str, SchemeVerdictOut] = {}
    # The details still empty, behind the profile percentage.
    missing: list[str] = []


class TableFilterOut(BaseModel):
    key: str
    label: str
    count: int


class TableOut(BaseModel):
    columns: list[TableColumnOut]
    rows: list[TableRowOut]
    filters: list[TableFilterOut]
    total: int
    page: int
    page_size: int


class ProfileSpreadOut(BaseModel):
    # counts[p] = how many families are exactly p% complete (p = 0..100).
    counts: list[int]
    total: int
    average: float
    # Standard deviation: how widely the percentages are spread around the average.
    spread: float


@router.get("/profile-spread", response_model=ProfileSpreadOut)
def profile_spread(session: Session = Depends(get_session)) -> ProfileSpreadOut:
    """How complete the profiles are across all families, for the bell curve."""
    return ProfileSpreadOut(**family_table.profile_spread(session))


@router.get("/table", response_model=TableOut)
def families_table(
    q: str = "",
    filter: str = Query("all", description="all, no_documents or no_phone"),
    sort: str = "primary_contact_name",
    descending: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> TableOut:
    """One page of the families, as rows and columns."""
    result = family_table.page(
        session,
        query=q,
        filter_key=filter if filter in family_table.FILTERS else "all",
        sort=sort,
        descending=descending,
        page_number=page,
        page_size=page_size,
    )
    return TableOut(
        columns=[
            TableColumnOut(
                key=c.key, label=c.label, kind=c.kind, editable=c.editable,
                sortable=c.sortable, required=c.required, choices=list(c.choices),
                group=c.group,
            )
            for c in result.columns
        ],
        rows=[TableRowOut(**r) for r in result.rows],
        filters=[
            TableFilterOut(key=k, label=v, count=result.counts.get(k, 0))
            for k, v in family_table.FILTERS.items()
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{family_id}/row", response_model=TableRowOut)
def family_row(family_id: int, session: Session = Depends(get_session)) -> TableRowOut:
    """One family as a table row, for opening it straight from a link."""
    family = session.get(Family, family_id)
    if family is None or family.is_draft:
        raise HTTPException(404, "That family was not found.")
    return _row_out(session, family)


def _row_out(session: Session, family: Family) -> TableRowOut:
    return TableRowOut(
        **family_table.rows(session, [family], family_table.columns(session))[0]
    )


class CellIn(BaseModel):
    key: str
    # Blank clears the box (the old value stays in history).
    value: str | None = None


class CellOut(BaseModel):
    changed: bool
    row: TableRowOut


@router.patch("/{family_id}/cell", response_model=CellOut)
def edit_cell(
    family_id: int, body: CellIn, session: Session = Depends(get_session)
) -> CellOut:
    """Correct one value. The old value is kept in field history."""
    family = session.get(Family, family_id)
    if family is None or family.is_draft:
        raise HTTPException(404, "That family was not found.")
    user = current_user(session)
    try:
        changed = family_table.edit_cell(
            session, family, body.key, body.value, user.id if user else None
        )
    except family_table.CellProblem as e:
        raise HTTPException(422, str(e)) from e
    session.commit()
    session.refresh(family)
    return CellOut(changed=changed, row=_row_out(session, family))


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
