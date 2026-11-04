"""Saved Assistant chats and the question log. Everything is rolled back."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import AuditLog

TABLE = {
    "kind": "table", "title": "Widow names starting with A", "columns": ["Name"],
    "rows": [["Amudha Gounder"], ["Anita Kumar"]], "count": 2, "truncated": False,
    "sql": "SELECT 1", "message": None, "options": [], "error": None,
}


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_start_add_open_and_list(client):
    started = client.post("/api/chats", json={"question": "names with A", "answer": TABLE}).json()
    assert started["title"] == "names with A"

    client.post(f"/api/chats/{started['id']}/messages",
                json={"question": "list them", "answer": TABLE})

    opened = client.get(f"/api/chats/{started['id']}").json()
    assert [m["question"] for m in opened["messages"]] == ["names with A", "list them"]
    assert opened["messages"][0]["answer"]["rows"] == TABLE["rows"]

    recent = client.get("/api/chats").json()
    assert recent[0]["id"] == started["id"]


def test_long_question_gets_a_short_title(client):
    started = client.post("/api/chats", json={"question": "x " * 100, "answer": TABLE}).json()
    assert len(started["title"]) <= 80 and started["title"].endswith("…")


def test_question_log_has_no_rows(client, tx_db):
    started = client.post("/api/chats", json={"question": "names with A", "answer": TABLE}).json()
    log = tx_db.scalars(
        select(AuditLog).where(AuditLog.action == "assistant.ask", AuditLog.entity_id == started["id"])
    ).all()
    assert len(log) == 1
    assert log[0].details["question"] == "names with A"
    assert log[0].details["sql"] == "SELECT 1"
    assert "rows" not in log[0].details


def test_delete(client):
    started = client.post("/api/chats", json={"question": "names with A", "answer": TABLE}).json()
    assert client.delete(f"/api/chats/{started['id']}").status_code == 204
    assert client.get(f"/api/chats/{started['id']}").status_code == 404
    assert client.post(f"/api/chats/{started['id']}/messages",
                       json={"question": "x", "answer": TABLE}).status_code == 404
