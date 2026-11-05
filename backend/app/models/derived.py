"""Facts worked out by our own code, stored so the chatbot's searches can use them.

CEA eligibility comes from the rules in app/services/cea.py, and a child's
class number from the same parser the CEA screen uses. Neither is a plain
column, so the chatbot could not search on them. These tables hold the
results; app/services/derived.py fills them and keeps them up to date. Every
row here can be rebuilt from the real data at any time: nothing is entered by
hand, and nothing is lost by emptying them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChildFacts(Base):
    """One row per child: class number, and CEA for the year that can be claimed now."""

    __tablename__ = "child_facts"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("family_members.id", ondelete="CASCADE"), primary_key=True
    )
    # 0 = KG, 1-12 = school class, 13 = after school (college, ITI...), -1 = not studying.
    class_number: Mapped[int | None] = mapped_column(Integer)
    cea_year: Mapped[str | None] = mapped_column(String(20))
    # "eligible", "not eligible", "eligible later" or "details missing".
    cea_status: Mapped[str | None] = mapped_column(String(30))
    cea_reason: Mapped[str | None] = mapped_column(Text)
    cea_amount: Mapped[int | None] = mapped_column(Integer)  # rupees for the whole year


class CeaByYear(Base):
    """CEA for one child for one academic year, for a few years either side."""

    __tablename__ = "cea_by_year"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("family_members.id", ondelete="CASCADE"), primary_key=True
    )
    academic_year: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int | None] = mapped_column(Integer)
    age_at_start: Mapped[int | None] = mapped_column(Integer)
    class_number: Mapped[int | None] = mapped_column(Integer)


class DerivedState(Base):
    """When the derived tables were last rebuilt, and from what state of the data."""

    __tablename__ = "derived_state"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
