"""Correcting a row, or leaving it out, before importing.

Everything here rolls back.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db import get_session
from tests.decide import take_the_sheet_via_api
from app.main import app
from app.models import Family, FieldHistory, ImportBatch
from app.models.enums import ChangeSource


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


HEADERS = [
    "Name of Widow", "Husband Name", "Army No", "Mob No",
    "Date of Casualty", "Distt", "State", "Annual Income (Rs)",
]

GOOD = [
    "Zzz Editwidow", "Zzz Editsoldier", "1212121A", "9876511111",
    "14-03-2021", "Rohtak", "Haryana", "90000",
]
SECOND = [
    "Zzz Otherwidow", "Zzz Othersoldier", "1313131B", "9876522222",
    "15-03-2021", "Hisar", "Haryana", "80000",
]


def workbook_bytes(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def start(client, rows) -> tuple[int, dict]:
    """Upload, confirm the mapping, and take the first preview."""
    uploaded = client.post(
        "/api/imports/upload",
        files={
            "file": (
                "edit_test.xlsx",
                workbook_bytes(rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()
    import_id = uploaded["import_id"]
    mapping = {
        c["source_heading"]: c["target_key"] or "__ignore__"
        for c in uploaded["columns"]
    }
    client.put(f"/api/imports/{import_id}/mapping", json={"mapping": mapping})
    preview = client.post(f"/api/imports/{import_id}/preview").json()
    return import_id, preview


# --- what the preview offers --------------------------------------------------


def test_the_preview_lists_the_values_it_would_write(client):
    _, preview = start(client, [GOOD])
    fields = {f["field_key"]: f["value"] for f in preview["rows"][0]["fields"]}
    assert fields["widow_name"] == "Zzz Editwidow"
    assert fields["phone"] == "+919876511111"
    assert fields["date_of_death"] == "14-03-2021"
    assert all(f["edited"] is False for f in preview["rows"][0]["fields"])


# --- correcting a value -------------------------------------------------------


def test_a_corrected_value_shows_in_the_preview(client):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]

    updated = client.put(
        f"/api/imports/{import_id}/rows/{row}",
        json={"values": {"phone": "9876599999"}},
    )
    assert updated.status_code == 200, updated.text

    fields = {f["field_key"]: f for f in updated.json()["rows"][0]["fields"]}
    assert fields["phone"]["value"] == "+919876599999"
    assert fields["phone"]["edited"] is True
    # Everything he did not touch is unchanged.
    assert fields["district"]["value"] == "Rohtak"
    assert fields["district"]["edited"] is False


def test_a_correction_is_checked_the_same_way_as_the_file(client):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]

    body = client.put(
        f"/api/imports/{import_id}/rows/{row}",
        json={"values": {"phone": "12345", "date_of_death": "32-13-2021"}},
    ).json()

    messages = " ".join(p["message"] for p in body["rows"][0]["problems"])
    assert "You typed" in messages
    fields = {f["field_key"]: f["value"] for f in body["rows"][0]["fields"]}
    assert fields["phone"] == "", "a rejected value must not be kept"


def test_correcting_a_bad_value_clears_its_problem(client):
    bad = list(GOOD)
    bad[3] = "98765 4321"  # not a valid phone
    import_id, preview = start(client, [bad])
    row = preview["rows"][0]
    assert any(p["code"] == "invalid_phone" for p in row["problems"])

    fixed = client.put(
        f"/api/imports/{import_id}/rows/{row['row_number']}",
        json={"values": {"phone": "9876533333"}},
    ).json()
    assert fixed["rows"][0]["problems"] == []


def test_clearing_a_correction_goes_back_to_what_the_file_said(client):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]

    client.put(
        f"/api/imports/{import_id}/rows/{row}",
        json={"values": {"phone": "9876599999"}},
    )
    restored = client.put(
        f"/api/imports/{import_id}/rows/{row}", json={"values": {}, "skip": False}
    ).json()

    fields = {f["field_key"]: f for f in restored["rows"][0]["fields"]}
    assert fields["phone"]["value"] == "+919876511111"
    assert fields["phone"]["edited"] is False


def test_a_field_no_column_feeds_is_refused(client):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]
    response = client.put(
        f"/api/imports/{import_id}/rows/{row}",
        json={"values": {"bank_ifsc": "SBIN0001234"}},
    )
    assert response.status_code == 400


# --- leaving a row out --------------------------------------------------------


def test_a_skipped_row_is_marked_and_not_counted(client):
    import_id, preview = start(client, [GOOD, SECOND])
    row = preview["rows"][0]["row_number"]

    body = client.put(
        f"/api/imports/{import_id}/rows/{row}", json={"skip": True}
    ).json()
    assert body["rows"][0]["action"] == "excluded"
    assert body["rows"][0]["skipped_by_user"] is True
    assert body["counts"]["excluded"] == 1
    assert body["counts"]["create"] == 1, "the other row should still be imported"


def test_a_skipped_row_is_not_written(client, tx_db):
    import_id, preview = start(client, [GOOD, SECOND])
    row = preview["rows"][0]["row_number"]
    client.put(f"/api/imports/{import_id}/rows/{row}", json={"skip": True})

    result = client.post(f"/api/imports/{import_id}/commit").json()
    assert result["excluded"] == 1
    assert result["created"] == 1

    assert (
        tx_db.scalars(
            select(Family).where(Family.primary_contact_name == "Zzz Editwidow")
        ).first()
        is None
    )
    assert (
        tx_db.scalars(
            select(Family).where(Family.primary_contact_name == "Zzz Otherwidow")
        ).first()
        is not None
    )


def test_unskipping_brings_the_row_back(client):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]
    client.put(f"/api/imports/{import_id}/rows/{row}", json={"skip": True})
    body = client.put(
        f"/api/imports/{import_id}/rows/{row}", json={"skip": False}
    ).json()
    assert body["rows"][0]["action"] == "create"


# --- importing with corrections ----------------------------------------------


def test_the_corrected_value_is_what_gets_saved(client, tx_db):
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]
    client.put(
        f"/api/imports/{import_id}/rows/{row}",
        json={"values": {"phone": "9876577777", "district": "Jind"}},
    )

    result = client.post(f"/api/imports/{import_id}/commit").json()
    assert result["created"] == 1

    family = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Editwidow")
    ).first()
    assert family.primary_phone == "+919876577777"
    assert family.district == "Jind"


def test_the_original_file_is_left_alone(client, tx_db):
    """Corrections live on the upload record, never in his spreadsheet."""
    import_id, preview = start(client, [GOOD])
    row = preview["rows"][0]["row_number"]
    client.put(
        f"/api/imports/{import_id}/rows/{row}", json={"values": {"district": "Jind"}}
    )

    batch = tx_db.get(ImportBatch, import_id)
    tx_db.refresh(batch)
    assert batch.row_overrides[str(row)]["values"]["district"] == "Jind"

    # Reading the stored file again still gives the original value.
    from app.services.excel_reader import read_sheet
    from app.services.storage import get_storage

    with get_storage().open(batch.storage_key) as handle:
        sheet = read_sheet(handle, batch.original_filename)
    assert "Rohtak" in sheet.rows[0]


def test_history_says_the_colonel_changed_it_not_the_file(client, tx_db):
    """Otherwise the record would claim the sheet said something it did not."""
    family = tx_db.scalars(select(Family).where(Family.is_draft.is_(False))).first()
    if family is None or family.soldier is None:
        pytest.skip("No seeded family to update")

    soldier = family.soldier
    if not soldier.service_number or not soldier.date_of_death:
        pytest.skip("Seeded family is missing the details needed to match")

    existing_row = [
        family.primary_contact_name,
        soldier.full_name,
        soldier.service_number,
        "9876544444",
        soldier.date_of_death.strftime("%d-%m-%Y"),
        family.district or "",
        family.state or "",
        "111111",
    ]
    import_id, preview = start(client, [existing_row])
    row = preview["rows"][0]
    assert row["action"] == "update"

    # He overrides the phone the sheet gave.
    client.put(
        f"/api/imports/{import_id}/rows/{row['row_number']}",
        json={"values": {"phone": "9876566666"}},
    )
    take_the_sheet_via_api(client, import_id)
    result = client.post(f"/api/imports/{import_id}/commit").json()
    assert result["fields_corrected"] >= 1

    history = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "primary_phone",
        ).order_by(FieldHistory.id.desc())
    ).first()
    assert history.new_value == "+919876566666"
    assert history.source == ChangeSource.officer_entry
    assert "preview" in (history.note or "").lower()

    # A field he did not touch is still recorded as coming from the file.
    income = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "annual_income",
        ).order_by(FieldHistory.id.desc())
    ).first()
    assert income.source == ChangeSource.excel_import


def test_a_correction_can_change_what_a_row_is(client, tx_db):
    """Fixing a service number can turn a new family into an update."""
    family = tx_db.scalars(select(Family).where(Family.is_draft.is_(False))).first()
    if family is None or family.soldier is None or not family.soldier.service_number:
        pytest.skip("No seeded family with a service number")

    soldier = family.soldier
    row_values = [
        family.primary_contact_name,
        soldier.full_name,
        "0000000Z",  # wrong service number
        "9876588888",
        soldier.date_of_death.strftime("%d-%m-%Y") if soldier.date_of_death else "",
        family.district or "",
        family.state or "",
        "222222",
    ]
    import_id, preview = start(client, [row_values])
    first_action = preview["rows"][0]["action"]

    corrected = client.put(
        f"/api/imports/{import_id}/rows/{preview['rows'][0]['row_number']}",
        json={"values": {"service_number": soldier.service_number}},
    ).json()

    assert corrected["rows"][0]["action"] == "update", (
        f"was {first_action}, should become an update once the number is right"
    )
    assert corrected["rows"][0]["matched_family_id"] == family.id
