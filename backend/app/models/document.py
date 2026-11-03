"""Documents uploaded for a family, and what AI read out of them."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import DocumentStatus, DocumentType


class Document(Base, TimestampMixin):
    """A file plus the AI's reading of it. AI suggests; an officer approves."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_members.id", ondelete="SET NULL")
    )

    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False, index=True
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        default=DocumentStatus.missing,
        nullable=False,
        index=True,
    )

    # One of the family's 1 to 4 supporting documents: the files he attaches
    # himself, which can be added to the end of a printed claim (e.g. CEA).
    is_supporting: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Key in the storage interface (local disk now, S3-compatible later).
    storage_key: Mapped[str | None] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(300))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    # What OCR + the LLM pulled out, and how sure they were (0-100).
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    extraction_confidence: Mapped[int | None] = mapped_column(Integer)
    # Fields where the document disagrees with the database.
    mismatches: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    family: Mapped["Family"] = relationship(back_populates="documents")


from app.models.family import Family  # noqa: E402
