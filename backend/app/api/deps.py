"""Shared dependencies for the API.

There is no login yet. Until there is, every action is attributed to the
colonel so the audit log and field history still make sense.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import UserRole


def current_user(session: Session) -> User | None:
    """TEMPORARY: the colonel. Replaced by real authentication later."""
    return session.scalar(select(User).where(User.role == UserRole.colonel))
