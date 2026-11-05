"""The chatbot's simple views, the CEA facts behind them, and the safety around searches.

Everything is rolled back, so the development database is left as it was.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db import get_session
from app.main import app
from app.models import AnswerFeedback, CeaByYear, ChildFacts, Family
from app.services import ask
from app.services.ask import Plan, Turn, answer_question, check_sql, run_query
from app.services.derived import ensure_fresh, is_fresh, refresh
from app.services.tools import cea_tool

TODAY = date.today()


# --- the derived facts --------------------------------------------------------


def test_refresh_matches_the_cea_rules(tx_db):
    """child_facts says the same as the CEA tool (the real rules) for the claimable year."""
    refresh(tx_db)
    eligible = tx_db.scalar(
        select(func.count()).select_from(ChildFacts).where(ChildFacts.cea_status == "eligible")
    )
    year = tx_db.scalar(select(ChildFacts.cea_year).limit(1))
    assert eligible == cea_tool(tx_db, year, TODAY).count
    # Several years are worked out, so "eligible by 2028" can be asked.
    years = tx_db.scalars(select(CeaByYear.academic_year).distinct()).all()
    assert len(years) >= 4


def test_rebuilt_only_when_the_data_changes(tx_db):
    ensure_fresh(tx_db)
    assert is_fresh(tx_db)
    assert ensure_fresh(tx_db) is False  # nothing changed: nothing rebuilt
    family = tx_db.scalar(select(Family).limit(1))
    family.notes = (family.notes or "") + " changed"
    tx_db.flush()
    assert not is_fresh(tx_db)
    assert ensure_fresh(tx_db) is True


def test_views_hold_readable_values(tx_db):
    refresh(tx_db)
    stages = set(tx_db.scalars(text("SELECT DISTINCT stage FROM ask.applications")).all())
    assert stages and all("_" not in stage for stage in stages)
    statuses = set(tx_db.scalars(text("SELECT DISTINCT cea_status FROM ask.children")).all())
    assert statuses <= {"eligible", "not eligible", "eligible later", "details missing", None}
    seasons = set(tx_db.scalars(text("SELECT DISTINCT season FROM ask.deaths")).all())
    # Empty when the date of death is not recorded.
    assert seasons <= {"winter", "summer", "monsoon", "post-monsoon", None}


# --- safety -------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM public.users",
        "SELECT * FROM pg_catalog.pg_roles",
        "SELECT * FROM information_schema.tables",
        "SELECT pg_read_file('x')",
    ],
)
def test_searches_cannot_reach_past_the_views(sql):
    with pytest.raises(ValueError):
        check_sql(sql)


def test_a_raw_table_name_does_not_resolve(tx_db):
    """Only the ask views are on the search path: 'users' is not one of them."""
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        run_query(tx_db, "SELECT full_name, email FROM users")
    # ...while a view of the same family data works.
    columns, rows, _ = run_query(tx_db, "SELECT widow_name FROM families")
    assert columns == ["widow_name"] and rows


# --- retries ------------------------------------------------------------------


def test_nothing_found_gets_one_more_look(monkeypatch, tx_db):
    """A search with no rows is shown back ("no rows", never data) for a second try."""
    calls = []

    def plan(self, question, today, history=None, failed=None):
        calls.append(failed)
        if failed is None:
            return Plan(tool="search", title="t", understood="u",
                        sql="SELECT widow_name FROM families WHERE district = 'Nowhere'")
        return Plan(tool="search", title="t", understood="u", sql="SELECT widow_name FROM families")

    monkeypatch.setattr(ask.MockQuestionLLM, "plan", plan)
    answer = answer_question(tx_db, "anything")
    assert answer.kind == "table" and answer.count > 0
    assert calls[0] is None and "no rows" in calls[1][1]


def test_gemini_busy_then_the_next_try(monkeypatch, tx_db):
    tries = []

    def plan(self, question, today, history=None, failed=None):
        tries.append(1)
        if len(tries) == 1:
            return Plan(tool="unreachable", message=ask.UNREACHABLE)
        return Plan(tool="reply", message="Hello")

    monkeypatch.setattr(ask.MockQuestionLLM, "plan", plan)
    answer = answer_question(tx_db, "hi")
    assert answer.kind == "message" and len(tries) == 2


def test_gemini_down_every_time_says_so(monkeypatch, tx_db):
    monkeypatch.setattr(
        ask.MockQuestionLLM, "plan",
        lambda self, q, today, history=None, failed=None: Plan(tool="unreachable", message=ask.UNREACHABLE),
    )
    answer = answer_question(tx_db, "hi")
    assert answer.kind == "error" and "could not reach" in answer.error


def test_understood_line_is_carried_through(monkeypatch, tx_db):
    monkeypatch.setattr(
        ask.MockQuestionLLM, "plan",
        lambda self, q, today, history=None, failed=None: Plan(
            tool="search", title="Families", understood="Every family", sql="SELECT family_code FROM families",
        ),
    )
    answer = answer_question(tx_db, "all families")
    assert answer.understood == "Every family"


# --- feedback -----------------------------------------------------------------


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_feedback_keeps_how_it_was_found_but_never_rows(client, tx_db):
    answer = {
        "kind": "table", "title": "Widows", "understood": "Widow names", "sql": "SELECT 1",
        "rows": [["Amudha Gounder", "+919876543210"]], "columns": ["Name", "Phone"], "count": 1,
    }
    reply = client.post("/api/ask/feedback", json={
        "question": "names with A", "rating": -1, "note": "wanted only Punjab", "answer": answer,
    })
    assert reply.status_code == 200
    saved = tx_db.scalar(select(AnswerFeedback).order_by(AnswerFeedback.id.desc()))
    assert saved.rating == -1 and saved.note == "wanted only Punjab"
    assert saved.answer["understood"] == "Widow names"
    assert "rows" not in saved.answer and "Amudha" not in str(saved.answer)

    wrong = client.get("/api/ask/feedback?rating=-1").json()
    assert wrong[0]["question"] == "names with A"


def test_feedback_rating_must_be_up_or_down(client):
    reply = client.post("/api/ask/feedback", json={"question": "x", "rating": 5, "answer": {}})
    assert reply.status_code == 400


def test_history_still_never_carries_rows():
    assert set(Turn.__dataclass_fields__) == {"question", "title", "sql", "reply", "tool"}
