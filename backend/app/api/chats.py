"""Saved Assistant chats: the Recent list, reopening a chat, and the question log.

There is no login, so every chat is shared. Each question is also written to
the audit log (when, what was asked, which tool answered, the search used) —
without the rows, which stay only in the chat itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_session
from app.models import AuditLog, Chat, ChatMessage

router = APIRouter(prefix="/api/chats", tags=["assistant"])

RECENT_LIMIT = 30
TITLE_LENGTH = 80


class MessageIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # The answer exactly as the screen received it from /api/ask.
    answer: dict[str, Any]


class ChatSummary(BaseModel):
    id: int
    title: str
    updated_at: str  # DD-MM-YYYY HH:MM


class MessageOut(BaseModel):
    question: str
    answer: dict[str, Any]


class ChatOut(BaseModel):
    id: int
    title: str
    messages: list[MessageOut]


def _title(question: str) -> str:
    question = " ".join(question.split())
    return question if len(question) <= TITLE_LENGTH else question[: TITLE_LENGTH - 1] + "…"


def _summary(chat: Chat) -> ChatSummary:
    return ChatSummary(id=chat.id, title=chat.title, updated_at=chat.updated_at.strftime("%d-%m-%Y %H:%M"))


def _add(session: Session, chat: Chat, body: MessageIn) -> None:
    position = session.scalar(
        select(func.coalesce(func.max(ChatMessage.position), 0)).where(ChatMessage.chat_id == chat.id)
    ) or 0
    session.add(ChatMessage(chat_id=chat.id, position=position + 1,
                            question=body.question, answer=body.answer))
    chat.updated_at = datetime.now(timezone.utc)

    answer = body.answer
    user = current_user(session)
    session.add(AuditLog(
        user_id=user.id if user else None,
        action="assistant.ask",
        entity_type="chat",
        entity_id=chat.id,
        occurred_at=datetime.now(timezone.utc),
        # The question and how it was answered — never the rows.
        details={
            "question": body.question,
            "kind": answer.get("kind"),
            "title": answer.get("title"),
            "sql": answer.get("sql"),
            "count": answer.get("count"),
            "error": answer.get("error"),
        },
    ))


@router.get("", response_model=list[ChatSummary])
def recent(session: Session = Depends(get_session)) -> list[ChatSummary]:
    chats = session.scalars(select(Chat).order_by(Chat.updated_at.desc()).limit(RECENT_LIMIT)).all()
    return [_summary(c) for c in chats]


@router.post("", response_model=ChatSummary)
def start(body: MessageIn, session: Session = Depends(get_session)) -> ChatSummary:
    """A new chat, with its first question and answer."""
    chat = Chat(title=_title(body.question))
    session.add(chat)
    session.flush()
    _add(session, chat, body)
    session.commit()
    return _summary(chat)


@router.post("/{chat_id}/messages", response_model=ChatSummary)
def add_message(chat_id: int, body: MessageIn, session: Session = Depends(get_session)) -> ChatSummary:
    chat = session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "That chat no longer exists.")
    _add(session, chat, body)
    session.commit()
    return _summary(chat)


@router.get("/{chat_id}", response_model=ChatOut)
def open_chat(chat_id: int, session: Session = Depends(get_session)) -> ChatOut:
    chat = session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "That chat no longer exists.")
    return ChatOut(
        id=chat.id,
        title=chat.title,
        messages=[MessageOut(question=m.question, answer=m.answer) for m in chat.messages],
    )


@router.delete("/{chat_id}", status_code=204, response_class=Response)
def delete_chat(chat_id: int, session: Session = Depends(get_session)) -> Response:
    chat = session.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "That chat no longer exists.")
    session.delete(chat)
    user = current_user(session)
    session.add(AuditLog(
        user_id=user.id if user else None,
        action="assistant.delete_chat",
        entity_type="chat",
        entity_id=chat_id,
        occurred_at=datetime.now(timezone.utc),
        details={"title": chat.title},
    ))
    session.commit()
    return Response(status_code=204)
