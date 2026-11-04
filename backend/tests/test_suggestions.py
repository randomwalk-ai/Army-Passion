"""Suggested questions: the daily choice, and that every answer agrees with its card."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, get_session
from app.main import app
from app.services import suggestions as sg
from app.services.suggestions import (
    ALWAYS,
    HOW_MANY,
    TYPES,
    Suggestion,
    answer_suggestion,
    planned_types,
    todays_suggestions,
)

DAY = date(2026, 11, 3)
DAYS = [DAY + timedelta(days=n) for n in range(60)]


@pytest.fixture
def session():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


# --- the daily plan (no database needed) -------------------------------------


def test_same_day_gives_the_same_plan():
    assert planned_types(DAY) == planned_types(DAY)


def test_plan_is_two_general_and_two_specific_with_no_repeats():
    for day in DAYS:
        plan = planned_types(day)
        assert len(set(plan)) == 4
        assert sum(k in sg.ROTATING_GENERAL for k in plan) == 2
        assert sum(k in sg.SPECIFIC for k in plan) == 2


def test_nothing_planned_yesterday_is_planned_today():
    for day in DAYS:
        assert not set(planned_types(day)) & set(planned_types(day - timedelta(days=1)))


def test_the_plan_changes_from_day_to_day():
    assert len({tuple(planned_types(day)) for day in DAYS}) > 5


# --- choosing what to show ----------------------------------------------------


def _fake_types(monkeypatch, empty=()):
    """Every type shows a card (except `empty`), with no database involved."""
    fake = []
    for t in TYPES:
        card = (lambda s, d: None) if t.key in empty else (
            lambda s, d, k=t.key, g=t.group: Suggestion(k, g, k)
        )
        fake.append(sg.SuggestionType(t.key, t.group, card, t.answer))
    monkeypatch.setattr(sg, "BY_KEY", {t.key: t for t in fake})
    monkeypatch.setattr(sg, "TYPES", fake)


def test_five_shown_with_stuck_first(monkeypatch):
    _fake_types(monkeypatch)
    for day in DAYS:
        keys = [s.key for s in todays_suggestions(None, day)]
        assert len(keys) == HOW_MANY == len(set(keys))
        assert keys[0] == ALWAYS
        assert keys[1:] == planned_types(day)


def test_empty_types_are_replaced(monkeypatch):
    _fake_types(monkeypatch, empty={"latest_import", "birthdays"})
    for day in DAYS:
        keys = [s.key for s in todays_suggestions(None, day)]
        assert len(keys) == HOW_MANY
        assert "latest_import" not in keys and "birthdays" not in keys


def test_no_stuck_applications_means_no_stuck_card(monkeypatch):
    _fake_types(monkeypatch, empty={ALWAYS})
    keys = [s.key for s in todays_suggestions(None, DAY)]
    assert ALWAYS not in keys
    assert len(keys) == HOW_MANY


# --- against the mock data ----------------------------------------------------


@pytest.mark.parametrize("kind", TYPES, ids=lambda t: t.key)
def test_every_search_runs_and_agrees_with_its_card(session, kind):
    card = kind.card(session, DAY)
    answer = answer_suggestion(session, kind.key, DAY)
    if card is None:
        assert answer.error
        return
    assert answer.kind == "table" and answer.error is None
    assert answer.rows
    assert all(len(row) == len(answer.columns) for row in answer.rows)
    if card.count is not None:
        assert answer.count == card.count


def test_unknown_suggestion(session):
    assert answer_suggestion(session, "nope", DAY).error


def test_api_lists_and_answers_suggestions(session):
    app.dependency_overrides[get_session] = lambda: session
    try:
        client = TestClient(app)
        cards = client.get("/api/ask/suggestions").json()
        assert 1 <= len(cards) <= HOW_MANY
        reply = client.post(f"/api/ask/suggestions/{cards[0]['key']}").json()
    finally:
        app.dependency_overrides.clear()
    assert reply["error"] is None and reply["rows"]
