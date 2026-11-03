"""Extra fields: information his sheets carry that we have no column for.

The database structure never changes. An approved extra field is recorded
here, and its value is stored in the family's `extra_fields` pocket.

This registry exists so that "Ward Member Name", "Ward member" and
"WardMemberName" do not become three different things. Once a field has been
approved, it is offered back the next time something similar turns up.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Extra fields are referred to in a mapping as "extra:ward_member_name",
# which keeps them apart from the built-in fields.
EXTRA_PREFIX = "extra:"


def slugify(label: str) -> str:
    """'Ward Member Name!' -> 'ward_member_name'"""
    lowered = label.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return cleaned[:60]


class CustomField(Base, TimestampMixin):
    """One approved extra field."""

    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The stable name used in the pocket and in mappings.
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    # What the colonel sees, e.g. "Ward member name".
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Where it came from, so its origin can be traced.
    first_seen_as: Mapped[str | None] = mapped_column(String(200))
    created_from_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
