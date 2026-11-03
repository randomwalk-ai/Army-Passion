"""CEA claims: who can claim, the pre-filled form, saving it, and the PDF."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user
from app.api.documents import supporting_documents
from app.db import get_session
from app.models import Family
from app.models.enums import DOCUMENT_TYPE_LABELS
from app.services.cea import (
    AcademicYear,
    ELIGIBLE,
    ELIGIBLE_LATER,
    NEEDS_DATA,
    NOT_ELIGIBLE,
    FamilyVerdict,
    ensure_cea_scheme,
    evaluate_family,
)
from app.services.cea_form import (
    CeaForm,
    FormProblem,
    build_form,
    missing_fields,
    render_pdf,
    save_form,
)
from app.services.document_pack import Attachment, append_documents
from app.services.storage import get_storage

router = APIRouter(prefix="/api/cea", tags=["cea"])

STATUS_LABELS = {
    ELIGIBLE: "Can claim",
    NEEDS_DATA: "Details missing",
    ELIGIBLE_LATER: "Can claim later",
    NOT_ELIGIBLE: "Cannot claim",
}


class ChildVerdictOut(BaseModel):
    member_id: int | None
    name: str
    status: str
    status_label: str
    reasons: list[str]
    to_confirm: list[str]
    age: int | None
    amount: int


class FamilyVerdictOut(BaseModel):
    family_id: int
    family_code: str
    nok_name: str
    soldier_name: str | None
    soldier_rank: str | None
    district: str | None
    state: str | None
    status: str
    status_label: str
    reasons: list[str]
    amount: int
    children: list[ChildVerdictOut]


class YearOption(BaseModel):
    label: str
    is_default: bool


class EligibilityResponse(BaseModel):
    academic_year: str
    years: list[YearOption]
    counts: dict[str, int]
    total_amount: int
    families: list[FamilyVerdictOut]
    rules_summary: list[str]


class FormResponse(BaseModel):
    form: CeaForm
    family: FamilyVerdictOut
    missing: list[str]


class SaveResponse(BaseModel):
    changed: list[str]
    form: CeaForm
    missing: list[str]


class SaveIn(BaseModel):
    form: CeaForm


class SaveProblem(BaseModel):
    problems: dict[str, str] = Field(default_factory=dict)


def _year(session: Session, label: str | None) -> tuple[AcademicYear, dict]:
    rules = ensure_cea_scheme(session).rules
    start_month = rules.get("academic_year_start_month", 4)
    if not label:
        return AcademicYear.last_completed(date.today(), start_month), rules
    try:
        return AcademicYear.parse(label, start_month), rules
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def _verdict_out(family: Family, verdict: FamilyVerdict) -> FamilyVerdictOut:
    soldier = family.soldier
    return FamilyVerdictOut(
        family_id=family.id,
        family_code=family.family_code,
        nok_name=family.primary_contact_name,
        soldier_name=soldier.full_name if soldier else None,
        soldier_rank=soldier.rank if soldier else None,
        district=family.district,
        state=family.state,
        status=verdict.status,
        status_label=STATUS_LABELS[verdict.status],
        reasons=verdict.reasons,
        amount=verdict.total,
        children=[
            ChildVerdictOut(
                member_id=c.member_id,
                name=c.name,
                status=c.status,
                status_label=STATUS_LABELS[c.status],
                reasons=c.reasons,
                to_confirm=c.to_confirm,
                age=c.age,
                amount=c.total if c.status == ELIGIBLE else 0,
            )
            for c in verdict.children
        ],
    )


def _family(session: Session, family_id: int) -> Family:
    family = session.scalar(
        select(Family)
        .where(Family.id == family_id)
        .options(selectinload(Family.members), selectinload(Family.soldier))
    )
    if family is None:
        raise HTTPException(404, "That family was not found.")
    return family


def rules_summary(rules: dict) -> list[str]:
    """The rules in plain words, read from the data so they never go stale."""
    latest = max(rules["rates"], key=lambda r: r["from"])
    since = date.fromisoformat(latest["from"]).strftime("%b %Y")
    return [
        f"The {rules['eldest_children']} eldest children only",
        f"KG to Class {rules['max_class']}, up to age {rules['max_age']}",
        f"From {AcademicYear(rules['first_academic_year']).label} onwards",
        f"₹{latest['cea']:,} a month per child since {since}; hostel ₹{latest['hostel']:,} a month extra",
        f"Divyang child: ₹{latest['divyang']:,} a month",
    ]


@router.get("/eligibility", response_model=EligibilityResponse)
def eligibility(
    year: str | None = Query(None, description="Academic year, e.g. 2025-26"),
    session: Session = Depends(get_session),
) -> EligibilityResponse:
    """Every family, checked against the CEA rules for one academic year."""
    academic_year, rules = _year(session, year)
    session.commit()  # keeps the scheme row if it was just created

    families = session.scalars(
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
        .order_by(Family.primary_contact_name)
    ).all()

    results = [_verdict_out(f, evaluate_family(f, academic_year, rules)) for f in families]
    # Most useful first: who can claim, then who needs details filled in.
    order = {ELIGIBLE: 0, NEEDS_DATA: 1, ELIGIBLE_LATER: 2, NOT_ELIGIBLE: 3}
    results.sort(key=lambda r: (order[r.status], r.nok_name))

    counts = {status: 0 for status in order}
    for r in results:
        counts[r.status] += 1

    default = AcademicYear.last_completed(date.today(), academic_year.start_month)
    years = [
        YearOption(label=AcademicYear(y).label, is_default=y == default.start_year)
        for y in range(default.start_year, rules["first_academic_year"] - 1, -1)
    ]
    return EligibilityResponse(
        academic_year=academic_year.label,
        years=years,
        counts=counts,
        total_amount=sum(r.amount for r in results),
        families=results,
        rules_summary=rules_summary(rules),
    )


@router.get("/families/{family_id}/form", response_model=FormResponse)
def get_form(
    family_id: int,
    year: str | None = None,
    session: Session = Depends(get_session),
) -> FormResponse:
    academic_year, rules = _year(session, year)
    family = _family(session, family_id)
    verdict = evaluate_family(family, academic_year, rules)
    form = build_form(family, verdict, academic_year, date.today())
    return FormResponse(
        form=form, family=_verdict_out(family, verdict), missing=missing_fields(form)
    )


@router.put(
    "/families/{family_id}/form",
    response_model=SaveResponse,
    responses={422: {"model": SaveProblem}},
)
def save(
    family_id: int, body: SaveIn, session: Session = Depends(get_session)
) -> SaveResponse:
    """His edits go back into the family's record. Old values stay in history."""
    if body.form.family_id != family_id:
        raise HTTPException(422, "This form belongs to a different family.")
    academic_year, rules = _year(session, body.form.academic_year)
    family = _family(session, family_id)
    original = build_form(
        family, evaluate_family(family, academic_year, rules), academic_year, date.today()
    )
    user = current_user(session)
    try:
        # Nothing is written until every value has been checked.
        changed = save_form(session, family, body.form, original, user.id if user else None)
    except FormProblem as e:
        raise HTTPException(422, {"message": str(e), "problems": e.problems}) from e
    session.commit()
    return SaveResponse(changed=changed, form=body.form, missing=missing_fields(body.form))


class PdfIn(SaveIn):
    # Add the family's supporting documents after the form pages.
    include_documents: bool = False


@router.post("/pdf")
def pdf(body: PdfIn, session: Session = Depends(get_session)) -> Response:
    """The filled claim pack, from exactly what is on his screen."""
    content = render_pdf(body.form)
    if body.include_documents:
        content = append_documents(content, _attachments(session, body.form.family_id))
    name = "".join(ch for ch in body.form.nok_name if ch.isalnum() or ch == " ").strip()
    filename = f"CEA {body.form.academic_year} - {name or 'claim'}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _attachments(session: Session, family_id: int | None) -> list[Attachment]:
    if not family_id:
        return []
    storage = get_storage()
    out = []
    for document in supporting_documents(session, family_id):
        content = None
        if document.storage_key and storage.exists(document.storage_key):
            with storage.open(document.storage_key) as handle:
                content = handle.read()
        out.append(
            Attachment(
                label=DOCUMENT_TYPE_LABELS.get(document.doc_type.value, "Document"),
                filename=document.original_filename or "document",
                mime_type=document.mime_type or "application/pdf",
                content=content,
            )
        )
    return out
