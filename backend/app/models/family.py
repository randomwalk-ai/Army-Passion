"""Families, their members, and where they live."""

from __future__ import annotations

from datetime import date
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import Language, Relation


class Family(Base, TimestampMixin):
    """One family = the dependants of one deceased soldier.

    `family_code` is the human-friendly identifier the colonel's office uses.
    """

    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    soldier_id: Mapped[int] = mapped_column(
        ForeignKey("soldiers.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Primary point of contact, usually the widow.
    primary_contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_phone: Mapped[str | None] = mapped_column(String(20), index=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(20))
    whatsapp_opted_in: Mapped[bool] = mapped_column(default=False, nullable=False)
    preferred_language: Mapped[Language] = mapped_column(
        Enum(Language, name="language"), default=Language.hindi, nullable=False
    )

    # How the next of kin is related to the soldier (wife, mother, father...).
    nok_relationship: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))

    address_line: Mapped[str | None] = mapped_column(String(400))
    # Holds the VILLAGE. The name is historical; the colonel's sheet keeps
    # village and town as separate columns, so town has its own field below.
    village_or_town: Mapped[str | None] = mapped_column(String(160))
    town: Mapped[str | None] = mapped_column(String(160))
    tehsil: Mapped[str | None] = mapped_column(String(120))
    post_office: Mapped[str | None] = mapped_column(String(160))
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10))
    # GPS of the house as given ("28.61, 77.20"), kept as text so a change
    # can be compared and recorded in history. `location` is derived from it
    # for the map.
    gps_coordinates: Mapped[str | None] = mapped_column(String(60))
    location: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )

    # Pension details. The grant forms ask for the PENSION account specifically.
    ppo_number: Mapped[str | None] = mapped_column(String(60), index=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(40))
    bank_ifsc: Mapped[str | None] = mapped_column(String(20))
    bank_name: Mapped[str | None] = mapped_column(String(160))
    bank_branch: Mapped[str | None] = mapped_column(String(200))

    # The soldier's unit, as a contact point for reaching the family.
    co_unit_name: Mapped[str | None] = mapped_column(String(200))
    co_unit_phone: Mapped[str | None] = mapped_column(String(20))

    # --- needed by the CEA claim form, not in the colonel's sheet ---
    # Left empty in the mock data for now; to be filled later.
    record_office: Mapped[str | None] = mapped_column(String(300))
    bank_account_holder: Mapped[str | None] = mapped_column(String(200))
    bank_address: Mapped[str | None] = mapped_column(String(400))
    correspondence_address: Mapped[str | None] = mapped_column(String(400))
    correspondence_pincode: Mapped[str | None] = mapped_column(String(10))
    nok_is_govt_servant: Mapped[bool | None] = mapped_column()

    monthly_pension_amount: Mapped[int | None] = mapped_column()
    annual_income: Mapped[int | None] = mapped_column()

    # Information his sheets carry that we have no column for. Keys are the
    # `key` of an approved CustomField, e.g. {"ward_member_name": "Suresh"}.
    # Using one JSON column means a new field never changes the table itself.
    extra_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # A draft is a family we have only partly heard about — usually from a
    # voice note. It is kept out of the main list until someone fills in the
    # gaps, so the real list never fills up with half-known records.
    is_draft: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    draft_source: Mapped[str | None] = mapped_column(String(80))

    # Set by an officer when the family's details were last confirmed by a human.
    last_verified_on: Mapped[date | None] = mapped_column(Date)
    last_contacted_on: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    soldier: Mapped["Soldier"] = relationship(back_populates="family")
    members: Mapped[list[FamilyMember]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )
    eligibilities: Mapped[list["FamilySchemeEligibility"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )


class FamilyMember(Base, TimestampMixin):
    """A dependant: the widow, children, parents."""

    __tablename__ = "family_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    relation: Mapped[Relation] = mapped_column(Enum(Relation, name="relation"), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, index=True)
    gender: Mapped[str | None] = mapped_column(String(20))

    is_studying: Mapped[bool | None] = mapped_column()
    education_level: Mapped[str | None] = mapped_column(String(120))
    is_married: Mapped[bool | None] = mapped_column()
    # As written in the colonel's sheet (Unmarried, Married...).
    marital_status: Mapped[str | None] = mapped_column(String(40))
    is_employed: Mapped[bool | None] = mapped_column()
    has_disability: Mapped[bool] = mapped_column(default=False, nullable=False)

    # --- needed by the CEA claim form, not in the colonel's sheet ---
    # Left empty in the mock data for now; to be filled later.
    current_class: Mapped[str | None] = mapped_column(String(40))
    academic_year: Mapped[str | None] = mapped_column(String(20))
    school_name: Mapped[str | None] = mapped_column(String(200))
    school_place: Mapped[str | None] = mapped_column(String(200))
    school_type: Mapped[str | None] = mapped_column(String(40))  # govt/aided/unaided
    school_board: Mapped[str | None] = mapped_column(String(120))
    school_affiliation_code: Mapped[str | None] = mapped_column(String(80))
    admission_number: Mapped[str | None] = mapped_column(String(60))
    roll_number: Mapped[str | None] = mapped_column(String(40))
    section: Mapped[str | None] = mapped_column(String(20))
    is_hostel: Mapped[bool | None] = mapped_column()

    aadhaar_last4: Mapped[str | None] = mapped_column(String(4))
    notes: Mapped[str | None] = mapped_column(Text)

    family: Mapped[Family] = relationship(back_populates="members")


from app.models.application import Application  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.interaction import Interaction  # noqa: E402
from app.models.people import Soldier  # noqa: E402
from app.models.scheme import FamilySchemeEligibility  # noqa: E402
