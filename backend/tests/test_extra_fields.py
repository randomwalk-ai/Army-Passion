"""Extra fields: columns his sheet has that our database has no place for.

The rule being tested throughout: the database STRUCTURE never changes. A new
field is recorded in a list and its values go into the family's pocket.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import inspect, select

from app.db import engine, get_session
from app.main import app
from app.models import CustomField, Family, FieldHistory, slugify


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


HEADERS = [
    "Name of Widow", "Husband Name", "Army No", "Mob No",
    "Distt", "State", "Ward Member Name", "Panchayat",
]


def workbook_bytes(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


ROW = [
    "Zzz Extrawidow", "Zzz Extrasoldier", "2222222X", "9876543210",
    "Rohtak", "Haryana", "Suresh Kumar", "Kotla",
]


def upload(client, rows=None):
    return client.post(
        "/api/imports/upload",
        files={
            "file": (
                "extra_sheet.xlsx",
                workbook_bytes(rows or [ROW]),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


# --- naming -------------------------------------------------------------------


def test_labels_become_tidy_keys():
    assert slugify("Ward Member Name") == "ward_member_name"
    assert slugify("  Panchayat!  ") == "panchayat"
    assert slugify("A/c Opening Date") == "a_c_opening_date"


# --- the list of approved fields ---------------------------------------------


def test_adding_an_extra_field(client):
    # A name of its own, so a field left over from a real import cannot
    # change what this test sees.
    response = client.post(
        "/api/custom-fields",
        json={"label": "Zzz Test Officer", "first_seen_as": "Zzz Test Officer"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == "zzz_test_officer"
    assert body["label"] == "Zzz Test Officer"


def test_the_same_field_is_never_added_twice(client):
    first = client.post("/api/custom-fields", json={"label": "Panchayat"}).json()
    # Different spelling, same thing.
    second = client.post("/api/custom-fields", json={"label": "  panchayat "})
    assert second.status_code == 201
    assert second.json()["key"] == first["key"]

    listed = client.get("/api/custom-fields").json()
    assert len([f for f in listed if f["key"] == "panchayat"]) == 1


def test_a_name_with_no_letters_is_refused(client):
    assert client.post("/api/custom-fields", json={"label": "!!!!"}).status_code == 400


# --- using them in an import --------------------------------------------------


def _map_everything(client, columns, extras: dict[str, str]):
    """extras maps a sheet heading to an approved extra field key."""
    mapping = {}
    for column in columns:
        heading = column["source_heading"]
        if heading in extras:
            mapping[heading] = f"extra:{extras[heading]}"
        else:
            mapping[heading] = column["target_key"] or "__ignore__"
    return mapping


def test_an_unapproved_extra_field_is_refused(client):
    body = upload(client).json()
    mapping = _map_everything(
        client, body["columns"], {"Panchayat": "not_approved_yet"}
    )
    response = client.put(
        f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping}
    )
    assert response.status_code == 400
    assert "has not been added yet" in response.json()["detail"]


def test_extra_values_are_stored_in_the_pocket(client, tx_db):
    client.post("/api/custom-fields", json={"label": "Ward member name"})
    client.post("/api/custom-fields", json={"label": "Panchayat"})

    body = upload(client).json()
    mapping = _map_everything(
        client,
        body["columns"],
        {"Ward Member Name": "ward_member_name", "Panchayat": "panchayat"},
    )
    assert (
        client.put(
            f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping}
        ).status_code
        == 200
    )
    assert client.post(f"/api/imports/{body['import_id']}/preview").status_code == 200
    result = client.post(f"/api/imports/{body['import_id']}/commit")
    assert result.status_code == 200, result.text
    assert result.json()["created"] == 1

    family = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Extrawidow")
    ).first()
    assert family is not None
    assert family.extra_fields == {
        "ward_member_name": "Suresh Kumar",
        "panchayat": "Kotla",
    }


def test_the_database_structure_does_not_change(client, tx_db):
    """The whole point: no new columns are ever created."""
    before = {c["name"] for c in inspect(engine).get_columns("families")}

    client.post("/api/custom-fields", json={"label": "Ward member name"})
    body = upload(client).json()
    mapping = _map_everything(
        client, body["columns"], {"Ward Member Name": "ward_member_name"}
    )
    client.put(f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping})
    client.post(f"/api/imports/{body['import_id']}/preview")
    client.post(f"/api/imports/{body['import_id']}/commit")

    after = {c["name"] for c in inspect(engine).get_columns("families")}
    assert before == after, "an extra field changed the table structure"


def test_changing_an_extra_value_keeps_the_old_one(client, tx_db):
    """The never-overwrite rule applies to extra fields too."""
    client.post("/api/custom-fields", json={"label": "Panchayat"})

    # First import.
    body = upload(client).json()
    mapping = _map_everything(client, body["columns"], {"Panchayat": "panchayat"})
    client.put(f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping})
    client.post(f"/api/imports/{body['import_id']}/preview")
    client.post(f"/api/imports/{body['import_id']}/commit")

    family = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Extrawidow")
    ).first()
    assert family.extra_fields["panchayat"] == "Kotla"

    # Same family, the panchayat has changed.
    changed = list(ROW)
    changed[7] = "Nangal"
    body2 = upload(client, [changed]).json()
    mapping2 = _map_everything(client, body2["columns"], {"Panchayat": "panchayat"})
    client.put(f"/api/imports/{body2['import_id']}/mapping", json={"mapping": mapping2})

    preview = client.post(f"/api/imports/{body2['import_id']}/preview").json()
    row = preview["rows"][0]
    assert row["action"] == "update"
    change = next(c for c in row["changes"] if c["field_name"] == "extra.panchayat")
    assert change["old_value"] == "Kotla"
    assert change["new_value"] == "Nangal"
    assert change["label"] == "Panchayat"

    client.post(f"/api/imports/{body2['import_id']}/commit")
    tx_db.expire_all()

    family = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Extrawidow")
    ).first()
    assert family.extra_fields["panchayat"] == "Nangal"

    history = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "extra.panchayat",
        )
    ).all()
    assert history, "the old extra value was not recorded"
    assert history[-1].old_value == "Kotla"
    assert history[-1].new_value == "Nangal"


def test_an_approved_field_is_offered_again_next_time(client):
    """So the same column does not become two slightly different fields."""
    client.post(
        "/api/custom-fields",
        json={"label": "Ward Member Name", "first_seen_as": "Ward Member Name"},
    )
    body = upload(client).json()
    guessed = {c["source_heading"]: c["target_key"] for c in body["columns"]}
    assert guessed["Ward Member Name"] == "extra:ward_member_name"


def test_extra_fields_appear_in_the_picker(client):
    client.post("/api/custom-fields", json={"label": "Panchayat"})
    body = upload(client).json()
    keys = {f["key"] for f in body["target_fields"]}
    assert "extra:panchayat" in keys
    groups = {f["group"] for f in body["target_fields"]}
    assert "Extra information" in groups


def test_usage_is_counted(client, tx_db):
    client.post("/api/custom-fields", json={"label": "Panchayat"})
    # The field may already exist from an earlier real import, so count the
    # change rather than assuming it starts at zero.
    before = tx_db.scalar(
        select(CustomField.times_used).where(CustomField.key == "panchayat")
    )
    body = upload(client).json()
    mapping = _map_everything(client, body["columns"], {"Panchayat": "panchayat"})
    client.put(f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping})
    client.post(f"/api/imports/{body['import_id']}/preview")
    client.post(f"/api/imports/{body['import_id']}/commit")

    tx_db.expire_all()
    after = tx_db.scalar(
        select(CustomField.times_used).where(CustomField.key == "panchayat")
    )
    assert after == before + 1


def test_retiring_a_field_keeps_the_values_already_stored(client, tx_db):
    client.post("/api/custom-fields", json={"label": "Panchayat"})
    body = upload(client).json()
    mapping = _map_everything(client, body["columns"], {"Panchayat": "panchayat"})
    client.put(f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping})
    client.post(f"/api/imports/{body['import_id']}/preview")
    client.post(f"/api/imports/{body['import_id']}/commit")

    assert client.delete("/api/custom-fields/panchayat").status_code == 200
    # Only that one stops being offered; others on the list are untouched.
    offered = {f["key"] for f in client.get("/api/custom-fields").json()}
    assert "panchayat" not in offered

    family = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Extrawidow")
    ).first()
    assert family.extra_fields["panchayat"] == "Kotla"
