"""The list of schemes, and how each one's answers reach the screens."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Family
from app.services import eligibility


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_every_scheme_answers_with_one_of_the_four_statuses(tx_db):
    families = eligibility.load_families(tx_db)
    for scheme in eligibility.SCHEMES:
        assert set(scheme.status_labels) == set(eligibility.STATUSES)
        verdicts = scheme.check(tx_db, families)
        assert set(verdicts) == {f.id for f in families}
        for verdict in verdicts.values():
            assert verdict.status in eligibility.STATUSES
            assert verdict.headline


def test_the_overview_counts_add_up_to_every_family(client):
    for scheme in client.get("/api/eligibility").json()["schemes"]:
        assert sum(c["count"] for c in scheme["counts"]) == scheme["families_checked"]
        assert [c["status"] for c in scheme["counts"]] == list(eligibility.STATUSES)


def test_the_cea_overview_agrees_with_the_cea_page(client):
    cea = next(s for s in client.get("/api/eligibility").json()["schemes"] if s["code"] == "CEA")
    page = client.get("/api/cea/eligibility").json()
    assert {c["status"]: c["count"] for c in cea["counts"]} == page["counts"]


def test_one_family_gets_an_answer_from_every_scheme(client, tx_db):
    family = tx_db.scalars(select(Family).where(Family.is_draft.is_(False))).first()
    answers = client.get(f"/api/families/{family.id}/eligibility").json()
    assert [a["code"] for a in answers] == [s.code for s in eligibility.SCHEMES]
    assert answers[0]["href"] == f"/cea/{family.id}"
    assert client.get("/api/families/999999/eligibility").status_code == 404


def test_the_table_has_a_column_and_a_verdict_for_each_scheme(client):
    body = client.get("/api/families/table?page_size=5").json()
    keys = [c["key"] for c in body["columns"]]
    for scheme in eligibility.SCHEMES:
        key = f"scheme.{scheme.code}"
        assert key in keys
        assert keys.index(key) == keys.index("documents") + 1 + eligibility.SCHEMES.index(scheme)
        for row in body["rows"]:
            assert row["eligibility"][scheme.code]["status"] == row["values"][key]
