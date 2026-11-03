"""Adding and removing whole columns from the preview.

Rolled back — the development database is left untouched.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Family, FieldHistory
from app.models.enums import ChangeSource


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


HEADERS = ["Name of Widow", "Husband Name", "Army No", "Mob No", "Distt", "State"]
ROW_A = ["Zzz Colwidow A", "Zzz Colsoldier A", "5151515A", "9876533301", "Rohtak", "Haryana"]
ROW_B = ["Zzz Colwidow B", "Zzz Colsoldier B", "5252525B", "9876533302", "Hisar", "Haryana"]


def workbook(rows) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def start(client, rows=(ROW_A, ROW_B)) -> int:
    up = client.post("/api/imports/upload", files={"file": ("cols.xlsx", workbook(rows))}).json()
    mapping = {c["source_heading"]: c["target_key"] or "__ignore__" for c in up["columns"]}
    client.put(f"/api/imports/{up['import_id']}/mapping", json={"mapping": mapping})
    client.post(f"/api/imports/{up['import_id']}/preview")
    return up["import_id"]


def family_named(tx_db, name):
    tx_db.expire_all()
    return tx_db.scalars(select(Family).where(Family.primary_contact_name == name)).first()


# --- what the preview reports ----------------------------------------------------


def test_the_preview_lists_its_columns_and_where_they_come_from(client):
    import_id = start(client)
    body = client.post(f"/api/imports/{import_id}/preview").json()
    by_key = {c["field_key"]: c for c in body["active_columns"]}
    assert by_key["phone"]["source_heading"] == "Mob No"
    assert by_key["phone"]["added"] is False
    assert by_key["widow_name"]["required"] is True


# --- removing a column -------------------------------------------------------------


def test_a_removed_column_is_not_imported(client, tx_db):
    import_id = start(client)
    body = client.put(
        f"/api/imports/{import_id}/columns", json={"remove_headings": ["Mob No"]}
    ).json()
    assert "phone" not in {c["field_key"] for c in body["active_columns"]}

    client.post(f"/api/imports/{import_id}/commit")
    assert family_named(tx_db, "Zzz Colwidow A").primary_phone is None


def test_a_required_column_cannot_be_removed(client):
    import_id = start(client)
    response = client.put(
        f"/api/imports/{import_id}/columns", json={"remove_headings": ["Name of Widow"]}
    )
    assert response.status_code == 400
    assert "no column for" in response.json()["detail"]


# --- adding a column ---------------------------------------------------------------


def test_an_added_column_with_one_value_fills_every_row(client, tx_db):
    import_id = start(client)
    body = client.put(
        f"/api/imports/{import_id}/columns",
        json={"add_fields": {"record_office": "Jat Regimental Centre, Bareilly"}},
    ).json()

    added = next(c for c in body["active_columns"] if c["field_key"] == "record_office")
    assert added["added"] is True
    assert added["source_heading"] is None
    for row in body["rows"]:
        field = next(f for f in row["fields"] if f["field_key"] == "record_office")
        assert field["value"] == "Jat Regimental Centre, Bareilly"

    client.post(f"/api/imports/{import_id}/commit")
    assert family_named(tx_db, "Zzz Colwidow A").record_office == "Jat Regimental Centre, Bareilly"
    assert family_named(tx_db, "Zzz Colwidow B").record_office == "Jat Regimental Centre, Bareilly"


def test_an_added_column_can_be_filled_row_by_row(client, tx_db):
    import_id = start(client)
    body = client.put(
        f"/api/imports/{import_id}/columns", json={"add_fields": {"bank_ifsc": ""}}
    ).json()
    row_a = next(r for r in body["rows"] if r["widow_name"] == "Zzz Colwidow A")

    client.put(
        f"/api/imports/{import_id}/rows/{row_a['row_number']}",
        json={"values": {"bank_ifsc": "SBIN0001234"}},
    )
    client.post(f"/api/imports/{import_id}/commit")

    assert family_named(tx_db, "Zzz Colwidow A").bank_ifsc == "SBIN0001234"
    assert family_named(tx_db, "Zzz Colwidow B").bank_ifsc is None


def test_a_row_value_wins_over_the_value_for_every_row(client, tx_db):
    import_id = start(client)
    body = client.put(
        f"/api/imports/{import_id}/columns",
        json={"add_fields": {"record_office": "Office X"}},
    ).json()
    row_b = next(r for r in body["rows"] if r["widow_name"] == "Zzz Colwidow B")
    client.put(
        f"/api/imports/{import_id}/rows/{row_b['row_number']}",
        json={"values": {"record_office": "Office Y"}},
    )
    client.post(f"/api/imports/{import_id}/commit")

    assert family_named(tx_db, "Zzz Colwidow A").record_office == "Office X"
    assert family_named(tx_db, "Zzz Colwidow B").record_office == "Office Y"


def test_added_values_are_recorded_as_typed_by_him(client, tx_db):
    """An added column did not come from the file, and history must not say it did."""
    family = tx_db.scalars(select(Family).where(Family.is_draft.is_(False))).first()
    soldier = family.soldier
    if not soldier or not soldier.service_number:
        pytest.skip("No seeded family to update")

    existing = [
        family.primary_contact_name, soldier.full_name, soldier.service_number,
        (family.primary_phone or "").replace("+91", ""), family.district or "", family.state or "",
    ]
    import_id = start(client, rows=[existing])
    client.put(
        f"/api/imports/{import_id}/columns",
        json={"add_fields": {"record_office": "Zzz Record Office"}},
    )
    client.post(f"/api/imports/{import_id}/commit")

    history = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "record_office",
        )
    ).first()
    assert history is not None
    assert history.source == ChangeSource.officer_entry


def test_a_field_already_in_the_sheet_cannot_be_added_again(client):
    import_id = start(client)
    response = client.put(
        f"/api/imports/{import_id}/columns", json={"add_fields": {"phone": "9999999999"}}
    )
    assert response.status_code == 400
    assert "already comes from a column" in response.json()["detail"]


def test_an_unknown_field_cannot_be_added(client):
    import_id = start(client)
    response = client.put(
        f"/api/imports/{import_id}/columns", json={"add_fields": {"no_such_field": ""}}
    )
    assert response.status_code == 400


def test_an_added_column_can_be_taken_away_again(client, tx_db):
    import_id = start(client)
    client.put(
        f"/api/imports/{import_id}/columns",
        json={"add_fields": {"record_office": "Office X"}},
    )
    body = client.put(
        f"/api/imports/{import_id}/columns", json={"remove_added": ["record_office"]}
    ).json()
    assert "record_office" not in {c["field_key"] for c in body["active_columns"]}

    client.post(f"/api/imports/{import_id}/commit")
    assert family_named(tx_db, "Zzz Colwidow A").record_office is None
