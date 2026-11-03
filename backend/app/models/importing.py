"""Excel uploads: the file, the agreed column mapping, and what happened.

An upload is not an import. The file is stored and read, the colonel confirms
what the columns mean and what will change, and only then are rows written.
This table holds that conversation so it survives a page refresh.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ImportStatus(str, enum.Enum):
    uploaded = "uploaded"  # file stored and read, columns guessed
    mapped = "mapped"  # he confirmed what the columns mean
    previewed = "previewed"  # he has seen what will change
    imported = "imported"  # rows written to the database
    cancelled = "cancelled"
    failed = "failed"


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status"),
        default=ImportStatus.uploaded,
        nullable=False,
        index=True,
    )

    sheet_name: Mapped[str | None] = mapped_column(String(200))
    header_row_number: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # The headings exactly as they appear in his file.
    headers: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    # What the system guessed: [{source_heading, column_index, target_key, ...}]
    guessed_mapping: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    # What he confirmed: {"Mob No": "phone", "S.No": "__ignore__", ...}
    confirmed_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # Corrections he made on the preview, keyed by the row number in his
    # sheet. His Excel file is never modified — these live only here, and
    # only for this upload.
    #   {"7": {"skip": false, "values": {"phone": "9876543210"}}}
    row_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    # Fields he added on the preview that are not a column in his sheet,
    # with an optional value for every row: {"bank_ifsc": "", "record_office": "..."}.
    added_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # Counts shown on the preview card, and the result after importing.
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class SavedColumnMapping(Base, TimestampMixin):
    """Remembers how a particular sheet layout was mapped last time.

    The colonel uploads the same sheet month after month. He should only have
    to explain its columns once.
    """

    __tablename__ = "saved_column_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # A fingerprint of the heading row, so the same layout is recognised again.
    headers_signature: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(200))
    headers: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    times_used: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
