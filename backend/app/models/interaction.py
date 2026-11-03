"""Calls, voice notes and visits — and what was extracted from them."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import InteractionType, Language


class Interaction(Base, TimestampMixin):
    """One contact with a family.

    Voice is transcribed in the original language, translated to English, then
    structured fields are extracted. All three are kept.
    """

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_type: Mapped[InteractionType] = mapped_column(
        Enum(InteractionType, name="interaction_type"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    language: Mapped[Language] = mapped_column(
        Enum(Language, name="language"), default=Language.hindi, nullable=False
    )
    transcript_original: Mapped[str | None] = mapped_column(Text)
    transcript_english: Mapped[str | None] = mapped_column(Text)
    summary_english: Mapped[str | None] = mapped_column(Text)

    # Structured facts the extractor found, e.g. {"son_started_college": true}.
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    # The talking points that were shown to the colonel before this call.
    talking_points_used: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    sentiment: Mapped[str | None] = mapped_column(String(40))
    follow_up_needed: Mapped[bool] = mapped_column(default=False, nullable=False)
    follow_up_note: Mapped[str | None] = mapped_column(Text)
    audio_storage_key: Mapped[str | None] = mapped_column(String(500))

    family: Mapped["Family"] = relationship(back_populates="interactions")


from app.models.family import Family  # noqa: E402
