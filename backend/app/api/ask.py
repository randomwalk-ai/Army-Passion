"""Typed questions and suggested questions on the Assistant screen."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
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
