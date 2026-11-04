"""merge: supporting documents (dashboard-and-cea) + assistant chats (dynamic-suggestions)

Both branches added a migration on top of b7d1e2f3a4c5. This joins them so
there is one line of history again. It changes nothing in the database.

Revision ID: e1f2a3b4c5d6
Revises: d4a9c1e8f2b6, d4e8a1c2f3b6
Create Date: 2026-11-04
"""
from collections.abc import Sequence

revision: str = "e1f2a3b4c5d6"
down_revision: tuple[str, ...] = ("d4a9c1e8f2b6", "d4e8a1c2f3b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
