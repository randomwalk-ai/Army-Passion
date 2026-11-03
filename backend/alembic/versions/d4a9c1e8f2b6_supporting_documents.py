"""supporting documents: the 1 to 4 files attached to each family

Revision ID: d4a9c1e8f2b6
Revises: b7d1e2f3a4c5
Create Date: 2026-11-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a9c1e8f2b6"
down_revision: str | None = "b7d1e2f3a4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("is_supporting", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_documents_supporting", "documents", ["family_id", "is_supporting"])


def downgrade() -> None:
    op.drop_index("ix_documents_supporting", table_name="documents")
    op.drop_column("documents", "is_supporting")
