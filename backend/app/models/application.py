"""Applications moving through the delivery pipeline, and their stage history."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ApplicationStage


class Application(Base, TimestampMixin):
    """One family applying to one scheme."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheme_id: Mapped[int] = mapped_column(
        ForeignKey("schemes.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    stage: Mapped[ApplicationStage] = mapped_column(
        Enum(ApplicationStage, name="application_stage"), nullable=False, index=True
    )
    # When the stage last changed — "stuck" is measured from here.
    stage_changed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # How many days in this stage before it counts as stuck.
    stuck_after_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    ksb_dak_id: Mapped[str | None] = mapped_column(String(60), index=True)
    amount_claimed: Mapped[int | None] = mapped_column(Integer)
    amount_credited: Mapped[int | None] = mapped_column(Integer)
    credited_on: Mapped[date | None] = mapped_column(Date)

    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    family: Mapped["Family"] = relationship(back_populates="applications")
    scheme: Mapped["Scheme"] = relationship()
    stage_events: Mapped[list[ApplicationStageEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStageEvent.occurred_at",
    )

    def days_in_stage(self, today: date) -> int:
        return (today - self.stage_changed_on).days

    def is_stuck(self, today: date) -> bool:
        terminal = {ApplicationStage.money_credited, ApplicationStage.rejected}
        if self.stage in terminal:
            return False
        return self.days_in_stage(today) > self.stuck_after_days


class ApplicationStageEvent(Base, TimestampMixin):
    """Append-only trail of every stage change. Nothing here is ever updated."""

    __tablename__ = "application_stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage: Mapped[ApplicationStage | None] = mapped_column(
        Enum(ApplicationStage, name="application_stage")
    )
    to_stage: Mapped[ApplicationStage] = mapped_column(
        Enum(ApplicationStage, name="application_stage"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="stage_events")


from app.models.family import Family  # noqa: E402
from app.models.scheme import Scheme  # noqa: E402
