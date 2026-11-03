"""more document types named by the grant forms

Revision ID: b7d1e2f3a4c5
Revises: 05752fe7fb67
Create Date: 2026-10-30

Autogenerate does not notice new values in a PostgreSQL enum, so they are
added by hand here.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b7d1e2f3a4c5"
down_revision: str | None = "05752fe7fb67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TYPES = [
    "service_booklet",
    "marksheet",
    "fee_receipt",
    "contingent_bill",
    "self_declaration",
    "cancelled_cheque",
    "computer_invoice",
    "passport_photo",
]


def upgrade() -> None:
    for value in NEW_TYPES:
        op.execute(f"ALTER TYPE document_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum without rebuilding the
    # type. The extra values are harmless if left in place.
    pass
