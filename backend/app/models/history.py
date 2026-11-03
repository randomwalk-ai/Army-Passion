"""The memory of the system: field history, audit log, and data-quality issues.

Rule from the brief: family data is NEVER overwritten silently. Every change to
a tracked field writes a row here first, with the old value, the new value,
where it came from, when, and who did it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import ChangeSource, IssueCode, IssueSeverity, IssueStatus


class FieldHistory(Base):
    """Append-only. One row per changed field."""

    __tablename__ = "field_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)  # "family", ...
    entity_id: Mapped[int] = mapped_column(nullable=False)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Kept as text so any column type can be recorded the same way.
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)

    source: Mapped[ChangeSource] = mapped_column(
        Enum(ChangeSource, name="change_source"), nullable=False
    )
    # e.g. the interaction or document the change came from.
    source_reference: Mapped[str | None] = mapped_column(String(200))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_field_history_entity", "entity_type", "entity_id", "changed_at"),
    )


class AuditLog(Base):
    """Who did what in the system. Append-only."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)  # "family.update", ...
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(60))


class DataQualityIssue(Base, TimestampMixin):
    """One problem found by the automatic checks. Feeds the "needs attention" list."""

    __tablename__ = "data_quality_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int] = mapped_column(nullable=False)
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )

    issue_code: Mapped[IssueCode] = mapped_column(
        Enum(IssueCode, name="issue_code"), nullable=False, index=True
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        Enum(IssueSeverity, name="issue_severity"),
        default=IssueSeverity.medium,
        nullable=False,
        index=True,
    )
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status"),
        default=IssueStatus.open,
        nullable=False,
        index=True,
    )

    field_name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
