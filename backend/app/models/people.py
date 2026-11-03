"""Users (staff), the deceased soldiers, and posting histories."""

from __future__ import annotations

from datetime import date

from geoalchemy2 import Geography
from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import DeathCauseCategory, DutyStatus, UserRole


class User(Base, TimestampMixin):
    """Staff: admin, the colonel, officers, volunteers."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    postings: Mapped[list[Posting]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Soldier(Base, TimestampMixin):
    """The deceased soldier. One soldier has one family record."""

    __tablename__ = "soldiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[str | None] = mapped_column(String(80))
    service_number: Mapped[str | None] = mapped_column(String(40), index=True)
    regiment: Mapped[str | None] = mapped_column(String(160))
    unit: Mapped[str | None] = mapped_column(String(160))

    date_of_birth: Mapped[date | None] = mapped_column(Date)
    date_of_enrolment: Mapped[date | None] = mapped_column(Date)
    date_of_death: Mapped[date | None] = mapped_column(Date, index=True)

    cause_category: Mapped[DeathCauseCategory | None] = mapped_column(
        Enum(DeathCauseCategory, name="death_cause_category")
    )
    cause_sub_category: Mapped[str | None] = mapped_column(String(160))
    place_of_death: Mapped[str | None] = mapped_column(String(200))
    district_of_death: Mapped[str | None] = mapped_column(String(120))
    state_of_death: Mapped[str | None] = mapped_column(String(120))
    weather_at_death: Mapped[str | None] = mapped_column(String(80))
    duty_status: Mapped[DutyStatus] = mapped_column(
        Enum(DutyStatus, name="duty_status"), default=DutyStatus.unknown, nullable=False
    )
    # Where the death happened, for the map and the seasonal-pattern insights.
    death_location: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )

    notes: Mapped[str | None] = mapped_column(Text)

    family: Mapped[Family | None] = relationship(back_populates="soldier", uselist=False)
    postings: Mapped[list[Posting]] = relationship(
        back_populates="soldier", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_soldiers_name_service", "full_name", "service_number"),
    )


class Posting(Base, TimestampMixin):
    """A place someone served, for a span of years.

    Belongs to EITHER a soldier or a user (the colonel's own postings). Overlaps
    between the two are what the talking-point engine looks for.
    """

    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    soldier_id: Mapped[int | None] = mapped_column(
        ForeignKey("soldiers.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    unit: Mapped[str] = mapped_column(String(160), nullable=False)
    formation: Mapped[str | None] = mapped_column(String(160))
    place: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    state: Mapped[str | None] = mapped_column(String(120))
    from_year: Mapped[int] = mapped_column(Integer, nullable=False)
    to_year: Mapped[int] = mapped_column(Integer, nullable=False)

    soldier: Mapped[Soldier | None] = relationship(back_populates="postings")
    user: Mapped[User | None] = relationship(back_populates="postings")


# Imported at the bottom to avoid a circular import at module load time.
from app.models.family import Family  # noqa: E402
