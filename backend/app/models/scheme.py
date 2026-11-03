"""Schemes and the eligibility results for each family.

Eligibility rules live in the `rules` JSON column — they are DATA, not code, so
new schemes can be added without a deploy. The engine that reads them is
deterministic and unit-tested.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import EligibilityStatus


class Scheme(Base, TimestampMixin):
    """A grant or welfare scheme a family can apply for."""

    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    authority: Mapped[str] = mapped_column(String(160), nullable=False)  # KSB, state board...
    category: Mapped[str | None] = mapped_column(String(80))  # education, medical, ...
    description: Mapped[str | None] = mapped_column(Text)

    benefit_amount: Mapped[int | None] = mapped_column(Integer)  # in rupees
    benefit_description: Mapped[str | None] = mapped_column(String(400))
    is_recurring: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Rules as data. Shape:
    #   {"all": [ {"field": "...", "op": "...", "value": ...}, ... ]}
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    required_documents: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    # TRUE for every scheme in the current phase. Real KSB/state rules come later.
    is_mock: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(400))

    eligibilities: Mapped[list[FamilySchemeEligibility]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan"
    )


class FamilySchemeEligibility(Base, TimestampMixin):
    """The engine's verdict for one family against one scheme.

    Recalculated on a schedule. `becomes_eligible_on` is what drives the
    "a child turns 18 next month" alert.
    """

    __tablename__ = "family_scheme_eligibility"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheme_id: Mapped[int] = mapped_column(
        ForeignKey("schemes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[EligibilityStatus] = mapped_column(
        Enum(EligibilityStatus, name="eligibility_status"), nullable=False, index=True
    )
    # Which rules passed and which failed, in plain language, for the officer to read.
    reasons: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    becomes_eligible_on: Mapped[date | None] = mapped_column(Date, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    family: Mapped["Family"] = relationship(back_populates="eligibilities")
    scheme: Mapped[Scheme] = relationship(back_populates="eligibilities")

    __table_args__ = (
        UniqueConstraint("family_id", "scheme_id", name="uq_family_scheme"),
    )


from app.models.family import Family  # noqa: E402
