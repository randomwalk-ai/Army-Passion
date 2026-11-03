"""A voice note that has been transcribed but not yet filed.

The colonel uploads audio, reads what the system heard, and only then decides
which family it belongs to. This table holds that in-between state, so a page
refresh does not lose the transcript.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import Language


class VoiceUploadStatus(str, enum.Enum):
    transcribed = "transcribed"  # heard, waiting for him to confirm
    saved = "saved"  # filed against a family
    discarded = "discarded"


class VoiceUpload(Base, TimestampMixin):
    __tablename__ = "voice_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[VoiceUploadStatus] = mapped_column(
        Enum(VoiceUploadStatus, name="voice_upload_status"),
        default=VoiceUploadStatus.transcribed,
        nullable=False,
        index=True,
    )

    language: Mapped[Language] = mapped_column(
        Enum(Language, name="language"), default=Language.english, nullable=False
    )
    transcript_original: Mapped[str | None] = mapped_column(Text)
    transcript_english: Mapped[str | None] = mapped_column(Text)
    summary_english: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(40), default="mock", nullable=False)

    # What the system thinks it heard: facts, sentiment, follow-up.
    suggested_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Filled in once he confirms.
    interaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("interactions.id", ondelete="SET NULL")
    )
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL")
    )
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
