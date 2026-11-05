"""The "Delete all data" button and the import progress bar. Everything is rolled back."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import AuditLog, Family, ImportBatch, ImportStatus, Scheme, User
from app.services import import_progress
from app.services.import_progress import ProgressTracker


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


# --- Delete all data ----------------------------------------------------------


def test_reset_is_off_by_default(client, tx_db, monkeypatch):
    monkeypatch.setattr(settings, "allow_data_reset", False)
    before = count(tx_db, Family)
    assert client.get("/api/admin/reset").json() == {"enabled": False}
    assert client.post("/api/admin/reset").status_code == 404
    assert count(tx_db, Family) == before


def test_reset_empties_families_but_keeps_users_and_schemes(client, tx_db, monkeypatch):
    monkeypatch.setattr(settings, "allow_data_reset", True)
    families, users, schemes = count(tx_db, Family), count(tx_db, User), count(tx_db, Scheme)
    assert families > 0, "needs the mock data to show something was removed"

    assert client.get("/api/admin/reset").json() == {"enabled": True}
    reply = client.post("/api/admin/reset")
    assert reply.status_code == 200
    assert reply.json() == {"families_removed": families}

    assert count(tx_db, Family) == 0
    assert count(tx_db, User) == users
    assert count(tx_db, Scheme) == schemes
    log = tx_db.scalars(select(AuditLog)).all()
    assert [entry.action for entry in log] == ["admin.delete_all_data"]


# --- Progress -----------------------------------------------------------------


def test_progress_endpoint_works_out_percent_and_time_left(client, tx_db):
    batch = ImportBatch(
        original_filename="p.xlsx", storage_key="none", status=ImportStatus.previewed,
        progress={"stage": "saving", "done": 500, "total": 1000, "elapsed": 10},
    )
    tx_db.add(batch)
    tx_db.flush()
    reply = client.get(f"/api/imports/{batch.id}/progress").json()
    assert reply == {"stage": "saving", "done": 500, "total": 1000, "percent": 50, "seconds_left": 10}


def test_progress_endpoint_when_nothing_is_running(client, tx_db):
    batch = ImportBatch(original_filename="p.xlsx", storage_key="none", status=ImportStatus.uploaded)
    tx_db.add(batch)
    tx_db.flush()
    assert client.get(f"/api/imports/{batch.id}/progress").json()["stage"] is None


def test_tracker_writes_a_few_times_not_once_per_row(monkeypatch):
    writes = []
    monkeypatch.setattr(import_progress, "write_progress", lambda _id, p: writes.append(p))
    tracker = ProgressTracker(import_id=1)
    for done in range(1, 1001):
        tracker.update("checking", done, 1000)
    for done in range(1, 1001):
        tracker.update("saving", done, 1000)
    tracker.clear()

    # First row of each stage, the last row of each stage, and the clear —
    # not 2,000 writes.
    assert len(writes) < 20
    assert writes[0]["stage"] == "checking" and writes[0]["done"] == 1
    assert any(w and w["stage"] == "saving" and w["done"] == 1000 for w in writes)
    assert writes[-1] is None
