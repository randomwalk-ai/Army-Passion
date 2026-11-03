"""Donors and the needs they are matched to."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Philanthropist(Base, TimestampMixin):
    """Someone willing to fund a family's need."""

    __tablename__ = "philanthropists"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    organisation: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(120))

    # Lists of enum values, e.g. ["education", "medical"].
    interests: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_states: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    annual_budget: Mapped[int | None] = mapped_column(Integer)
    max_per_family: Mapped[int | None] = mapped_column(Integer)
    wants_anonymity: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    matches: Mapped[list[PhilanthropistMatch]] = relationship(
        back_populates="philanthropist", cascade="all, delete-orphan"
    )


class PhilanthropistMatch(Base, TimestampMixin):
    """A proposed or agreed pairing between a donor and a family's need."""

    __tablename__ = "philanthropist_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    philanthropist_id: Mapped[int] = mapped_column(
        ForeignKey("philanthropists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )

    need_category: Mapped[str] = mapped_column(String(80), nullable=False)
    need_description: Mapped[str | None] = mapped_column(Text)
    amount_requested: Mapped[int | None] = mapped_column(Integer)
    amount_pledged: Mapped[int | None] = mapped_column(Integer)
    # proposed / accepted / declined / funded
    status: Mapped[str] = mapped_column(String(40), default="proposed", nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer)  # 0-100, from the matcher
    match_reasons: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    pledged_on: Mapped[date | None] = mapped_column(Date)

    philanthropist: Mapped[Philanthropist] = relationship(back_populates="matches")
