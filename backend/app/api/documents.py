"""Documents linked to a family, or to one person in it.

He picks the family, then whether the document belongs to the whole family
(service booklet, PPO) or to one child (mark sheet, fee receipt), picks the
type, and uploads. Files go through the storage interface: local disk now,
S3-compatible storage later.
"""

from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_session
from app.models import AuditLog, Document, Family, FamilyMember
from app.models.enums import DOCUMENT_TYPE_LABELS, DocumentStatus, DocumentType
from app.services.storage import get_storage

router = APIRouter(tags=["documents"])

IST = ZoneInfo("Asia/Kolkata")
ALLOWED_SUFFIXES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# Every family keeps between one and four supporting documents.
MIN_SUPPORTING = 1
MAX_SUPPORTING = 4


class MemberOut(BaseModel):
    member_id: int
    full_name: str
    relation: str
    date_of_birth: str | None  # DD-MM-YYYY


class DocumentTypeOut(BaseModel):
    key: str
    label: str


class DocumentOut(BaseModel):
    document_id: int
    family_id: int
    member_id: int | None
    # Who it belongs to, in words: "Whole family" or the person's name.
    belongs_to: str
    doc_type: str
    doc_type_label: str
    filename: str | None
    size_bytes: int | None
    status: str
    uploaded_on: str | None  # DD-MM-YYYY
    has_file: bool


def _label(doc_type: str) -> str:
    return DOCUMENT_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").capitalize())


def _out(document: Document, member_names: dict[int, str]) -> DocumentOut:
    storage = get_storage()
    has_file = bool(document.storage_key) and storage.exists(document.storage_key)
    return DocumentOut(
        document_id=document.id,
        family_id=document.family_id,
        member_id=document.family_member_id,
        belongs_to=(
            member_names.get(document.family_member_id, "A family member")
            if document.family_member_id
            else "Whole family"
        ),
        doc_type=document.doc_type.value,
        doc_type_label=_label(document.doc_type.value),
        filename=document.original_filename,
        size_bytes=document.size_bytes,
        status=document.status.value,
        uploaded_on=document.created_at.strftime("%d-%m-%Y") if document.created_at else None,
        has_file=has_file,
    )


async def _read_upload(file: UploadFile) -> tuple[str, str, bytes]:
    """The file's name, type and bytes, or a plain-words reason it can't be taken."""
    filename = file.filename or "document"
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="I can take PDF files and photos (.pdf, .jpg, .jpeg, .png, .webp).",
        )
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 20 MB.")
    return filename, ALLOWED_SUFFIXES[suffix], contents


def _family_or_404(session: Session, family_id: int) -> Family:
    family = session.get(Family, family_id)
    if family is None:
        raise HTTPException(status_code=404, detail="That family was not found.")
    return family


@router.get("/api/document-types", response_model=list[DocumentTypeOut])
def document_types() -> list[DocumentTypeOut]:
    """In the order the grant forms most often ask for them."""
    return [DocumentTypeOut(key=k, label=v) for k, v in DOCUMENT_TYPE_LABELS.items()]


@router.get("/api/families/{family_id}/members", response_model=list[MemberOut])
def family_members(
    family_id: int, session: Session = Depends(get_session)
) -> list[MemberOut]:
    """Who a document can be linked to."""
    family = _family_or_404(session, family_id)
    return [
        MemberOut(
            member_id=m.id,
            full_name=m.full_name,
            relation=m.relation.value,
            date_of_birth=m.date_of_birth.strftime("%d-%m-%Y") if m.date_of_birth else None,
        )
        for m in sorted(family.members, key=lambda m: (m.relation.value, m.full_name))
    ]


@router.get("/api/families/{family_id}/documents", response_model=list[DocumentOut])
def list_documents(
    family_id: int, session: Session = Depends(get_session)
) -> list[DocumentOut]:
    family = _family_or_404(session, family_id)
    names = {m.id: m.full_name for m in family.members}
    documents = session.scalars(
        select(Document)
        .where(Document.family_id == family_id)
        .order_by(Document.created_at.desc())
    ).all()
    return [_out(d, names) for d in documents]


@router.post("/api/families/{family_id}/documents", response_model=DocumentOut)
async def upload_document(
    family_id: int,
    file: UploadFile,
    doc_type: str = Form(...),
    member_id: int | None = Form(None),
    session: Session = Depends(get_session),
) -> DocumentOut:
    family = _family_or_404(session, family_id)

    try:
        kind = DocumentType(doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown document type '{doc_type}'.") from exc

    names = {m.id: m.full_name for m in family.members}
    if member_id is not None and member_id not in names:
        raise HTTPException(
            status_code=400, detail="That person is not a member of this family."
        )

    filename, mime_type, contents = await _read_upload(file)
    storage_key = get_storage().save(
        io.BytesIO(contents), filename, folder=f"documents/{family_id}"
    )

    user = current_user(session)
    document = Document(
        family_id=family_id,
        family_member_id=member_id,
        doc_type=kind,
        status=DocumentStatus.uploaded,
        storage_key=storage_key,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(contents),
    )
    session.add(document)
    session.flush()

    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action="document.upload",
            entity_type="family",
            entity_id=family_id,
            occurred_at=datetime.now(IST),
            details={
                "document_id": document.id,
                "doc_type": kind.value,
                "member_id": member_id,
                "filename": filename,
            },
        )
    )
    session.commit()
    return _out(document, names)


@router.get("/api/documents/{document_id}/file")
def download_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="That document was not found.")
    storage = get_storage()
    if not document.storage_key or not storage.exists(document.storage_key):
        raise HTTPException(
            status_code=404,
            detail="There is no file for this document (it may be a mock record).",
        )
    handle = storage.open(document.storage_key)
    name = document.original_filename or "document"
    return StreamingResponse(
        handle,
        media_type=document.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@router.delete("/api/documents/{document_id}")
def delete_document(document_id: int, session: Session = Depends(get_session)) -> dict:
    """For a file uploaded by mistake. The removal is recorded in the audit log."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="That document was not found.")

    user = current_user(session)
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action="document.delete",
            entity_type="family",
            entity_id=document.family_id,
            occurred_at=datetime.now(IST),
            details={
                "document_id": document.id,
                "doc_type": document.doc_type.value,
                "filename": document.original_filename,
                "member_id": document.family_member_id,
            },
        )
    )
    if document.storage_key:
        get_storage().delete(document.storage_key)
    session.delete(document)
    session.commit()
    return {"deleted": document_id}


# --- supporting documents: the 1 to 4 files he attaches to a family -----------


class SupportingDocumentsOut(BaseModel):
    family_id: int
    minimum: int
    maximum: int
    documents: list[DocumentOut]


def supporting_documents(session: Session, family_id: int) -> list[Document]:
    """Oldest first, so the order he added them is the order they print in."""
    return list(
        session.scalars(
            select(Document)
            .where(Document.family_id == family_id, Document.is_supporting.is_(True))
            .order_by(Document.created_at, Document.id)
        ).all()
    )


def _supporting_out(session: Session, family: Family) -> SupportingDocumentsOut:
    names = {m.id: m.full_name for m in family.members}
    return SupportingDocumentsOut(
        family_id=family.id,
        minimum=MIN_SUPPORTING,
        maximum=MAX_SUPPORTING,
        documents=[_out(d, names) for d in supporting_documents(session, family.id)],
    )


@router.get(
    "/api/families/{family_id}/supporting-documents",
    response_model=SupportingDocumentsOut,
)
def list_supporting(
    family_id: int, session: Session = Depends(get_session)
) -> SupportingDocumentsOut:
    return _supporting_out(session, _family_or_404(session, family_id))


@router.post(
    "/api/families/{family_id}/supporting-documents",
    response_model=SupportingDocumentsOut,
)
async def add_supporting(
    family_id: int,
    file: UploadFile,
    doc_type: str = Form("other"),
    session: Session = Depends(get_session),
) -> SupportingDocumentsOut:
    family = _family_or_404(session, family_id)
    try:
        kind = DocumentType(doc_type or "other")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown document type '{doc_type}'.") from exc

    if len(supporting_documents(session, family_id)) >= MAX_SUPPORTING:
        raise HTTPException(
            status_code=409,
            detail=f"This family already has {MAX_SUPPORTING} documents, the most it can have. "
            "Remove one first, then add the new one.",
        )

    filename, mime_type, contents = await _read_upload(file)
    storage_key = get_storage().save(
        io.BytesIO(contents), filename, folder=f"documents/{family_id}"
    )
    user = current_user(session)
    document = Document(
        family_id=family_id,
        doc_type=kind,
        status=DocumentStatus.uploaded,
        is_supporting=True,
        storage_key=storage_key,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(contents),
    )
    session.add(document)
    session.flush()
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action="document.upload",
            entity_type="family",
            entity_id=family_id,
            occurred_at=datetime.now(IST),
            details={
                "document_id": document.id,
                "doc_type": kind.value,
                "filename": filename,
                "supporting": True,
            },
        )
    )
    session.commit()
    return _supporting_out(session, family)


@router.delete(
    "/api/families/{family_id}/supporting-documents/{document_id}",
    response_model=SupportingDocumentsOut,
)
def remove_supporting(
    family_id: int, document_id: int, session: Session = Depends(get_session)
) -> SupportingDocumentsOut:
    family = _family_or_404(session, family_id)
    current = supporting_documents(session, family_id)
    document = next((d for d in current if d.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="That document was not found.")
    if len(current) <= MIN_SUPPORTING:
        raise HTTPException(
            status_code=409,
            detail="A family needs at least one document. Add the replacement first, "
            "then remove this one.",
        )
    delete_document(document_id, session)
    return _supporting_out(session, family)
