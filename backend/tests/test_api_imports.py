"""The upload endpoints, end to end through the real API.

These exist because the pieces can each be correct while the API that joins
them is not — a preview that builds fine can still fail to serialise.

Everything is rolled back, so the development database is left untouched.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Family, Soldier


@pytest.fixture
def client(tx_db):
    """An API client whose writes all roll back when the test ends."""
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


HEADERS = [
    "S.No", "Name of Widow", "Husband Name", "Army No", "Mob No",
    "Date of Casualty", "Distt", "State", "Annual Income (Rs)",
]


def workbook_bytes(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Widows List"
    sheet.append(["ZILA SAINIK BOARD - MOCK"])
    sheet.append([])
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def upload(client, rows):
    return client.post(
        "/api/imports/upload",
        files={
            "file": (
                "test_sheet.xlsx",
                workbook_bytes(rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def full_mapping(columns):
    return {
        c["source_heading"]: c["target_key"] or "__ignore__" for c in columns
    }


NEW_ROW = [
    1, "Zzz Apiwidow", "Zzz Apisoldier", "3333333A", "9876512345",
    "14-03-2021", "Rohtak", "Haryana", "90000",
]


# --- upload -------------------------------------------------------------------


def test_upload_reads_the_sheet_and_guesses_the_columns(client):
    response = upload(client, [NEW_ROW])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["row_count"] == 1
    assert body["header_row_number"] == 3
    guessed = {c["source_heading"]: c["target_key"] for c in body["columns"]}
    assert guessed["Name of Widow"] == "widow_name"
    assert guessed["Mob No"] == "phone"
    assert body["missing_required"] == []


def test_a_file_we_cannot_read_is_refused_politely(client):
    response = client.post(
        "/api/imports/upload",
        files={"file": ("notes.pdf", b"%PDF-1.4 not a sheet", "application/pdf")},
    )
    assert response.status_code == 400
    assert "Excel" in response.json()["detail"]


def test_an_empty_file_is_refused(client):
    response = client.post(
        "/api/imports/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400


# --- mapping ------------------------------------------------------------------


def test_two_columns_cannot_be_mapped_to_the_same_field(client):
    body = upload(client, [NEW_ROW]).json()
    mapping = full_mapping(body["columns"])
    mapping["Distt"] = "state"  # State is already taken
    response = client.put(
        f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping}
    )
    assert response.status_code == 400
    assert "pick one" in response.json()["detail"]


def test_a_column_that_does_not_exist_is_refused(client):
    body = upload(client, [NEW_ROW]).json()
    response = client.put(
        f"/api/imports/{body['import_id']}/mapping",
        json={"mapping": {"No Such Column": "phone"}},
    )
    assert response.status_code == 400


# --- order of operations ------------------------------------------------------


def test_preview_is_refused_before_the_columns_are_confirmed(client):
    body = upload(client, [NEW_ROW]).json()
    response = client.post(f"/api/imports/{body['import_id']}/preview")
    assert response.status_code == 409


def test_import_is_refused_before_the_preview_is_seen(client):
    body = upload(client, [NEW_ROW]).json()
    client.put(
        f"/api/imports/{body['import_id']}/mapping",
        json={"mapping": full_mapping(body["columns"])},
    )
    response = client.post(f"/api/imports/{body['import_id']}/commit")
    assert response.status_code == 409
    assert "preview" in response.json()["detail"].lower()


def test_the_same_sheet_cannot_be_imported_twice(client):
    import_id = _upload_map_preview(client, [NEW_ROW])
    assert client.post(f"/api/imports/{import_id}/commit").status_code == 200
    second = client.post(f"/api/imports/{import_id}/commit")
    assert second.status_code == 409


def test_an_unknown_upload_gives_a_clear_404(client):
    assert client.post("/api/imports/999999/preview").status_code == 404


# --- the whole journey --------------------------------------------------------


def _upload_map_preview(client, rows) -> int:
    body = upload(client, rows).json()
    import_id = body["import_id"]
    mapped = client.put(
        f"/api/imports/{import_id}/mapping",
        json={"mapping": full_mapping(body["columns"])},
    )
    assert mapped.status_code == 200, mapped.text
    previewed = client.post(f"/api/imports/{import_id}/preview")
    assert previewed.status_code == 200, previewed.text
    return import_id


def test_preview_of_a_new_person_says_create(client):
    body = upload(client, [NEW_ROW]).json()
    import_id = body["import_id"]
    client.put(
        f"/api/imports/{import_id}/mapping",
        json={"mapping": full_mapping(body["columns"])},
    )
    preview = client.post(f"/api/imports/{import_id}/preview").json()
    assert preview["counts"]["create"] == 1
    assert preview["rows"][0]["action"] == "create"


def test_preview_of_an_existing_family_returns_readable_changes(client, tx_db):
    """This is the case that broke once: nested change objects must serialise."""
    family = tx_db.scalars(
        select(Family)
        .join(Soldier, Soldier.id == Family.soldier_id)
        .where(
            Family.primary_phone.is_not(None),
            Soldier.service_number.is_not(None),
            Soldier.date_of_death.is_not(None),
        )
        .limit(1)
    ).first()
    if family is None:
        pytest.skip("No suitable seeded family — run seed.generate --reset")

    soldier = family.soldier
    row = [
        1,
        family.primary_contact_name,
        soldier.full_name,
        soldier.service_number,
        "9876599999",
        soldier.date_of_death.strftime("%d-%m-%Y"),
        family.district or "",
        family.state or "",
        "654321",
    ]

    body = upload(client, [row]).json()
    import_id = body["import_id"]
    client.put(
        f"/api/imports/{import_id}/mapping",
        json={"mapping": full_mapping(body["columns"])},
    )
    response = client.post(f"/api/imports/{import_id}/preview")
    assert response.status_code == 200, response.text

    preview = response.json()
    assert preview["counts"]["update"] == 1
    changes = preview["rows"][0]["changes"]
    assert changes, "an update with no listed changes is useless to him"
    by_field = {c["field_name"]: c for c in changes}
    assert by_field["primary_phone"]["new_value"] == "+919876599999"
    assert by_field["primary_phone"]["old_value"] == family.primary_phone
    assert by_field["primary_phone"]["label"] == "Phone number"


def test_importing_reports_what_it_did(client):
    import_id = _upload_map_preview(client, [NEW_ROW])
    response = client.post(f"/api/imports/{import_id}/commit")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] == 1
    assert result["status"] == "imported"
    assert len(result["new_family_codes"]) == 1


# --- remembering a layout -----------------------------------------------------


def _with_door_no() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS + ["Door No"])
    sheet.append(NEW_ROW + ["12-A"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _upload_door_no(client):
    response = client.post(
        "/api/imports/upload",
        files={"file": ("door.xlsx", _with_door_no(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_leave_out_counts_for_that_upload_only(client):
    first = _upload_door_no(client)
    mapping = full_mapping(first["columns"])
    assert mapping["Door No"] == "__ignore__"  # he chose "Leave out"
    saved = client.put(f"/api/imports/{first['import_id']}/mapping", json={"mapping": mapping})
    assert saved.status_code == 200, saved.text

    again = {c["source_heading"]: c for c in _upload_door_no(client)["columns"]}
    # Asked again next time, not silently skipped...
    assert again["Door No"]["target_key"] != "__ignore__"
    # ...while what we skip ourselves, and what was matched, is still remembered.
    assert again["S.No"]["target_key"] == "__ignore__"
    assert again["Name of Widow"]["reason"] == "You set this last time"
