"""Typed questions: the safety checks on generated SQL, memory, and a full run with the fake LLM."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal, get_session
from app.main import app
from app.models import Family
from app.services.ask import Plan, Turn, answer_question, build_prompt, check_sql, parse_plan


@pytest.fixture
def session():
    s = SessionLocal()
    yield s
    s.close()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select primary_contact_name from families;",
        "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
        # Forbidden words inside quotes or aliases are just text.
        "SELECT 'please delete me' AS \"Update\"",
        "SELECT updated_at, created_at FROM families",
    ],
)
def test_allowed_queries(sql):
    assert check_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM families",
        "UPDATE families SET notes = 'x'",
        "SELECT 1; DROP TABLE families",
        "INSERT INTO families DEFAULT VALUES",
        "WITH gone AS (DELETE FROM families RETURNING id) SELECT * FROM gone",
        "SELECT pg_sleep(60)",
        "SELECT 1 -- ;\n; DROP TABLE families",
        "TRUNCATE families",
    ],
)
def test_refused_queries(sql):
    with pytest.raises(ValueError):
        check_sql(sql)


def test_parse_plan_shapes():
    assert parse_plan('{"tool": "search", "title": "T", "sql": "SELECT 1"}') == Plan(
        tool="search", sql="SELECT 1", title="T"
    )
    # The older shape without "tool", wrapped in fences.
    assert parse_plan('```json\n{"sql": "SELECT 1"}\n```').sql == "SELECT 1"
    assert parse_plan('{"tool": "reply", "message": "Hello"}') == Plan(tool="reply", message="Hello")
    clarify = parse_plan(
        '{"tool": "clarify", "message": "Which?", "options": ["a", "b", "", "c", "d", "e"]}'
    )
    assert clarify.tool == "clarify" and clarify.options == ["a", "b", "c", "d"]
    assert parse_plan("not json").tool == "error"


def test_letter_question_lists_matching_families(session):
    answer = answer_question(
        session, 'How many families have the widow name starting with letter "A" list them'
    )
    expected = session.scalar(
        select(func.count())
        .select_from(Family)
        .where(Family.is_draft.is_(False), Family.primary_contact_name.ilike("A%"))
    )
    assert answer.kind == "table"
    assert answer.count == expected
    assert all(str(row[0]).upper().startswith("A") for row in answer.rows)


def test_writes_are_refused_by_the_database_too(monkeypatch, session):
    """Even if a change slipped past check_sql, the read-only transaction stops it."""
    from app.services import ask

    monkeypatch.setattr(ask, "check_sql", lambda sql: sql)
    monkeypatch.setattr(
        ask.MockQuestionLLM,
        "plan",
        lambda self, q, today, history=None, failed=None: Plan(
            tool="search",
            title="x",
            sql="WITH gone AS (DELETE FROM families RETURNING id) SELECT count(*) FROM gone",
        ),
    )
    before = session.scalar(select(func.count()).select_from(Family))
    answer = answer_question(session, "anything")
    after = session.scalar(select(func.count()).select_from(Family))
    assert answer.kind == "error"
    assert before == after


def test_greeting_gets_a_reply_not_an_error(session):
    answer = answer_question(session, "hi")
    assert answer.kind == "message" and answer.message


def test_follow_up_uses_the_earlier_search(session):
    """'how many ... A' then 'list them': the second answer lists what the first counted."""
    first = answer_question(session, "how many widow names start with A")
    history = [Turn(question="how many widow names start with A", title=first.title, sql=first.sql)]
    second = answer_question(session, "list them", history)
    assert first.kind == second.kind == "table"
    assert len(second.rows) == first.rows[0][0] > 1
    assert all(str(row[0]).upper().startswith("A") for row in second.rows)


def test_history_never_carries_rows():
    """What may reach the LLM: questions, titles, queries and replies — no rows."""
    prompt = build_prompt(
        "list them",
        date(2026, 11, 4),
        [Turn(question="how many start with A", title="Count", sql="SELECT 1")],
    )
    assert "how many start with A" in prompt and "SELECT 1" in prompt
    assert set(Turn.__dataclass_fields__) == {"question", "title", "sql", "reply", "tool"}


def _client(session):
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_api_unknown_question_in_mock_mode(session):
    try:
        response = _client(session).post("/api/ask", json={"question": "Who died in winter?"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["kind"] == "message"
    assert "LLM_PROVIDER" in response.json()["message"]


def test_api_passes_history(session):
    try:
        client = _client(session)
        first = client.post("/api/ask", json={"question": "how many widow names start with A"}).json()
        second = client.post(
            "/api/ask",
            json={
                "question": "list them",
                "history": [
                    {"question": "how many widow names start with A",
                     "title": first["title"], "sql": first["sql"]}
                ],
            },
        ).json()
    finally:
        app.dependency_overrides.clear()
    assert second["kind"] == "table" and second["count"] == first["rows"][0][0]


def test_cea_for_one_family_gives_a_verdict_per_child(session):
    """'is X eligible for cea' answers for that family, child by child."""
    from app.models import FamilyMember
    from app.models.enums import Relation

    code = session.scalar(
        select(Family.family_code)
        .join(FamilyMember, FamilyMember.family_id == Family.id)
        .where(Family.is_draft.is_(False), FamilyMember.relation.in_([Relation.son, Relation.daughter]))
        .limit(1)
    )
    answer = answer_question(session, f"is {code} eligible for cea")
    assert answer.kind == "table"
    assert code in answer.title
    assert answer.columns[:4] == ["Child", "Age", "CEA", "Why"]
    assert all(row[-1] == code for row in answer.rows)
    assert answer.tool and code in answer.tool


def test_unknown_name_offers_near_matches(session):
    """A name nobody has exactly gets 'did you mean' choices, not a dead end."""
    from app.services.tools import family_tool

    surname = session.scalar(
        select(Family.primary_contact_name).where(Family.is_draft.is_(False)).limit(1)
    ).split()[-1]
    answer = family_tool(session, f"Zzqxw {surname}", date(2026, 11, 4))
    assert answer.kind == "clarify"
    assert answer.options and all(surname.lower() in o.lower() for o in answer.options)


def test_latest_question_is_restated_for_follow_ups():
    prompt = build_prompt(
        "how about Sunanda Pawar?",
        date(2026, 11, 4),
        [Turn(question="is Meena Dagar eligible for cea", tool="cea for family AP-2026-0093")],
    )
    assert "MOST RECENT QUESTION" in prompt
    assert "cea for family AP-2026-0093" in prompt
