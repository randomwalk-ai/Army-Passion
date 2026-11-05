"""The "Delete all data" button on Home, for the demo site.

Switched on only when ALLOW_DATA_RESET is true (set on Render for the demo).
When it is off, the button is not shown and this endpoint refuses, so it can
never empty a database holding real families.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import settings
from app.db import get_session
from app.models import AuditLog, Family

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Everything about families goes; users, schemes and the officers' own
# postings stay, so the app still works on an empty database.
EMPTY_THE_DATABASE = [
    # The colonel's and officers' postings are kept; the soldiers' go.
    "DELETE FROM postings WHERE soldier_id IS NOT NULL",
    """TRUNCATE application_stage_events, applications, chat_messages, chats,
               data_quality_issues, documents, family_scheme_eligibility,
               voice_uploads, interactions, philanthropist_matches, philanthropists,
               family_members, families, field_history, audit_log
               RESTART IDENTITY""",
    "DELETE FROM soldiers",
    "UPDATE custom_fields SET created_from_import_id = NULL",
    "DELETE FROM import_batches",
]


class ResetStatus(BaseModel):
    enabled: bool


class ResetResult(BaseModel):
    families_removed: int


def reset_enabled() -> bool:
    return settings.allow_data_reset


@router.get("/reset", response_model=ResetStatus)
def reset_status() -> ResetStatus:
    """Whether Home shows the "Delete all data" button."""
    return ResetStatus(enabled=reset_enabled())


@router.post("/reset", response_model=ResetResult)
def reset(session: Session = Depends(get_session)) -> ResetResult:
    """Empty the database. All in one transaction: if anything fails, nothing goes."""
    if not reset_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    families = session.scalar(select(func.count()).select_from(Family)) or 0
    try:
        for statement in EMPTY_THE_DATABASE:
            session.execute(text(statement))
        # The audit log was just emptied; the reset itself is its first entry.
        user = current_user(session)
        session.add(AuditLog(
            user_id=user.id if user else None,
            action="admin.delete_all_data",
            occurred_at=datetime.now(timezone.utc),
            details={"families_removed": families},
        ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ResetResult(families_removed=families)
