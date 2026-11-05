"""Typed questions and suggested questions on the Assistant screen."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AnswerFeedback
from app.services.ask import MAX_HISTORY, Answer, Turn, answer_question
from app.services.export import answer_filename, build_answer_workbook
from app.services.suggestions import answer_suggestion, todays_suggestions

router = APIRouter(prefix="/api/ask", tags=["assistant"])


class TurnIn(BaseModel):
    """An earlier question in this chat. Never carries the rows that came back."""

    question: str = Field(max_length=1000)
    title: str | None = Field(default=None, max_length=300)
    sql: str | None = Field(default=None, max_length=4000)
    reply: str | None = Field(default=None, max_length=1000)
    tool: str | None = Field(default=None, max_length=300)


class AskRequest(BaseModel):
    question: str
    history: list[TurnIn] = Field(default_factory=list)


class AskResponse(BaseModel):
    # "table", "message", "clarify" or "error".
    kind: str
    title: str
    columns: list[str]
    rows: list[list[Any]]
    count: int
    truncated: bool
    # The query that was run. Not shown on screen, but sent back with the next
    # question so a follow-up ("list them") can build on it.
    sql: str | None
    message: str | None
    options: list[str]
    error: str | None
    # Which of our own tools answered (CEA, a family); sent back as history.
    tool: str | None = None
    # "I looked for: ...", shown above the answer.
    understood: str | None = None


class SuggestionOut(BaseModel):
    key: str
    group: str
    text: str
    count: int | None


def _response(answer: Answer) -> AskResponse:
    return AskResponse(**answer.__dict__)


@router.post("", response_model=AskResponse)
def ask(body: AskRequest, session: Session = Depends(get_session)) -> AskResponse:
    history = [Turn(**t.model_dump()) for t in body.history[-MAX_HISTORY:]]
    return _response(answer_question(session, body.question, history))


@router.get("/suggestions", response_model=list[SuggestionOut])
def suggestions(session: Session = Depends(get_session)) -> list[SuggestionOut]:
    return [SuggestionOut(**s.__dict__) for s in todays_suggestions(session)]


@router.post("/suggestions/{key}", response_model=AskResponse)
def suggestion_answer(key: str, session: Session = Depends(get_session)) -> AskResponse:
    return _response(answer_suggestion(session, key))


class ExportRequest(BaseModel):
    """What is already on the screen — this never re-runs a search."""

    title: str
    columns: list[str]
    rows: list[list[Any]]


@router.post("/export")
def export(body: ExportRequest) -> Response:
    if not body.rows:
        raise HTTPException(400, "Nothing to download.")
    content = build_answer_workbook(body.title, body.columns, body.rows)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{answer_filename(body.title)}"'},
    )


# --- thumbs up / down ------------------------------------------------------

# What is kept about the answer: how it was understood and found. Never rows.
FEEDBACK_KEEPS = ("kind", "title", "understood", "sql", "tool", "count", "message", "error")


class FeedbackIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    rating: int = Field(description="+1 (right) or -1 (wrong)")
    note: str | None = Field(default=None, max_length=1000)
    answer: dict[str, Any]


class FeedbackOut(BaseModel):
    id: int
    question: str
    rating: int
    note: str | None
    answer: dict[str, Any]
    created_at: str  # DD-MM-YYYY HH:MM


@router.post("/feedback", response_model=FeedbackOut)
def give_feedback(body: FeedbackIn, session: Session = Depends(get_session)) -> FeedbackOut:
    if body.rating not in (1, -1):
        raise HTTPException(400, "Rating must be 1 (right) or -1 (wrong).")
    kept = {key: body.answer.get(key) for key in FEEDBACK_KEEPS if key in body.answer}
    row = AnswerFeedback(question=body.question, rating=body.rating, note=body.note, answer=kept)
    session.add(row)
    session.commit()
    return _feedback_out(row)


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    rating: int | None = None, session: Session = Depends(get_session)
) -> list[FeedbackOut]:
    """The latest feedback; ?rating=-1 lists only the answers marked wrong."""
    query = select(AnswerFeedback).order_by(AnswerFeedback.created_at.desc()).limit(200)
    if rating in (1, -1):
        query = query.where(AnswerFeedback.rating == rating)
    return [_feedback_out(row) for row in session.scalars(query).all()]


def _feedback_out(row: AnswerFeedback) -> FeedbackOut:
    return FeedbackOut(
        id=row.id, question=row.question, rating=row.rating, note=row.note,
        answer=row.answer, created_at=row.created_at.strftime("%d-%m-%Y %H:%M"),
    )
