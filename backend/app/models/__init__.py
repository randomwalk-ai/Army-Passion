"""Importing this package registers every model on Base.metadata.

Alembic's autogenerate relies on that, so keep every model listed here.
"""

from app.models.application import Application, ApplicationStageEvent
from app.models.base import Base
from app.models.chat import Chat, ChatMessage
from app.models.custom_field import EXTRA_PREFIX, CustomField, slugify
from app.models.document import Document
from app.models.family import Family, FamilyMember
from app.models.history import AuditLog, DataQualityIssue, FieldHistory
from app.models.importing import ImportBatch, ImportStatus, SavedColumnMapping
from app.models.interaction import Interaction
from app.models.people import Posting, Soldier, User
from app.models.philanthropist import Philanthropist, PhilanthropistMatch
from app.models.scheme import FamilySchemeEligibility, Scheme
from app.models.voice import VoiceUpload, VoiceUploadStatus

__all__ = [
    "Application",
    "ApplicationStageEvent",
    "AuditLog",
    "Base",
    "Chat",
    "ChatMessage",
    "CustomField",
    "EXTRA_PREFIX",
    "DataQualityIssue",
    "Document",
    "Family",
    "FamilyMember",
    "FamilySchemeEligibility",
    "FieldHistory",
    "ImportBatch",
    "ImportStatus",
    "Interaction",
    "Philanthropist",
    "PhilanthropistMatch",
    "Posting",
    "SavedColumnMapping",
    "Scheme",
    "Soldier",
    "User",
    "slugify",
    "VoiceUpload",
    "VoiceUploadStatus",
]
