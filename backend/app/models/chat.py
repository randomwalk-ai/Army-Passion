"""Saved Assistant chats, so the colonel can reopen one from the Recent list.

There is no login, so every chat is shared by everyone who uses the app.
Each message stores the question as typed and the answer exactly as it was
shown (including its rows) — this is our own database, not the LLM.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The first question, shortened; shown in the Recent list.
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="ChatMessage.position",
    )


class ChatMessage(Base, TimestampMixin):
    """One question and the answer it got."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # The answer as the screen received it: kind, title, columns, rows, sql...
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class AnswerFeedback(Base, TimestampMixin):
    """A thumbs up or down on one chatbot answer.

    Kept so wrong answers can be looked at and turned into tests. Stores the
    question and how it was answered (title, search, tool), not the rows.
    """

    __tablename__ = "answer_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # +1 (right) or -1 (wrong).
    rating: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # kind, title, understood, sql, tool, count: never the rows themselves.
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
