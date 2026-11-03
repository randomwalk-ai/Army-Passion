"""The dashboard, the add-a-family form, and the CEA screens, through the API.

Everything is rolled back, so the development database is left untouched.
"""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Family, FamilyMember, FieldHistory


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


NEW_FAMILY = {
    "values": {
        "soldier_name": "Late Hav Test Kumar Zzyzx",
        "rank": "Havildar",
        "service_number": "TEST-0000001",
        "unit": "99 Test Regiment",
        "date_of_death": "12-08-2021",
        "widow_name": "Smt Testa Devi Zzyzx",
        "phone": "98765 43210",
        "district": "Testpur",
        "state": "Haryana",
        "pincode": "124001",
    },
    "children": [
        {"name": "Aarav Zzyzx", "sex": "M", "date_of_birth": "05-06-2013",
         "current_class": "Class 7", "school_name": "Test Public School", "school_place": "Testpur"},
        {"name": "", "sex": "", "date_of_birth": ""},
    ],
}


# --- dashboard --------------------------------------------------------------


def test_dashboard_lists_the_numbers(client):
    body = client.get("/api/dashboard").json()
    keys = [s["key"] for s in body["stats"]]
    assert keys[:2] == ["families", "applicants"]
    assert all(isinstance(s["value"], int) for s in body["stats"])


def test_dashboard_counts_a_new_family(client):
    before = _stat(client, "families")
    assert client.post("/api/families", json=NEW_FAMILY).status_code == 201
    assert _stat(client, "families") == before + 1


def _stat(client, key):
    return next(s["value"] for s in client.get("/api/dashboard").json()["stats"] if s["key"] == key)


# --- adding a family by hand -------------------------------------------------


def test_a_family_typed_in_is_saved_cleanly(client, tx_db):
    response = client.post("/api/families", json=NEW_FAMILY)
    assert response.status_code == 201, response.text
    family = tx_db.get(Family, response.json()["family_id"])

    assert family.primary_contact_name == "Testa Devi Zzyzx"  # "Smt" dropped
    assert family.primary_phone == "+919876543210"
    assert family.soldier.date_of_death.isoformat() == "2021-08-12"

    children = [m for m in family.members if m.relation.value == "son"]
    assert [c.full_name for c in children] == ["Aarav Zzyzx"]  # the blank row is ignored
    assert children[0].school_name == "Test Public School"

    created = tx_db.scalar(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id, FieldHistory.field_name == "__created__"
        )
    )
    assert created.source.value == "officer_entry"


def test_wrongly_typed_values_are_pointed_out_per_box(client):
    bad = {"values": {**NEW_FAMILY["values"], "phone": "12345", "date_of_death": "31-02-2021"}}
    response = client.post("/api/families", json=bad)
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert set(errors) == {"phone", "date_of_death"}


def test_names_are_required(client):
    response = client.post("/api/families", json={"values": {"district": "Testpur"}})
    assert set(response.json()["detail"]["errors"]) == {"soldier_name", "widow_name"}


def test_a_family_we_already_have_is_questioned_first(client):
    assert client.post("/api/families", json=NEW_FAMILY).status_code == 201
    again = client.post("/api/families", json=NEW_FAMILY)
    assert again.status_code == 409
    assert again.json()["detail"]["matches"][0]["score"] >= 80

    anyway = client.post("/api/families", json={**NEW_FAMILY, "confirm_not_duplicate": True})
    assert anyway.status_code == 201


def test_a_missing_phone_is_saved_but_flagged(client):
    values = {k: v for k, v in NEW_FAMILY["values"].items() if k != "phone"}
    response = client.post("/api/families", json={"values": values})
    assert response.status_code == 201
    assert response.json()["warnings"] == ["No phone number"]


# --- CEA -----------------------------------------------------------------------


def test_eligibility_puts_families_who_can_claim_first(client):
    body = client.get("/api/cea/eligibility?year=2025-26").json()
    assert body["academic_year"] == "2025-26"
    statuses = [f["status"] for f in body["families"]]
    assert statuses == sorted(
        statuses, key=["eligible", "needs_data", "eligible_later", "not_eligible"].index
    )
    assert sum(body["counts"].values()) == len(body["families"])
    assert body["years"][-1]["label"] == "2017-18"


def test_new_family_shows_up_as_able_to_claim(client):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    body = client.get("/api/cea/eligibility?year=2025-26").json()
    mine = next(f for f in body["families"] if f["family_id"] == family_id)
    assert mine["status"] == "eligible"
    assert mine["amount"] == 12 * 2813


def test_the_form_is_prefilled_from_the_record(client):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    body = client.get(f"/api/cea/families/{family_id}/form?year=2025-26").json()
    form = body["form"]
    assert form["nok_name"] == "Testa Devi Zzyzx"
    assert form["service_number"] == "TEST-0000001"
    assert form["children"][0]["name"] == "Aarav Zzyzx"
    assert form["children"][0]["cea_amount"] == 12 * 2813
    assert "Record office" in body["missing"]


def test_edits_on_the_form_are_saved_with_history(client, tx_db):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    form = client.get(f"/api/cea/families/{family_id}/form").json()["form"]
    form["record_office"] = "Test Records, Testpur Cantt"
    form["bank_ifsc"] = "sbin0001234"
    form["children"][0]["section"] = "B"

    response = client.put(f"/api/cea/families/{family_id}/form", json={"form": form})
    assert response.status_code == 200, response.text
    # Only what he typed (plus the year his school details belong to);
    # nothing we merely guessed, like correspondence address = home address.
    assert response.json()["changed"] == [
        "record office", "bank ifsc", "Aarav's section", "Aarav's academic year",
    ]

    family = tx_db.get(Family, family_id)
    assert family.record_office == "Test Records, Testpur Cantt"
    assert family.bank_ifsc == "SBIN0001234"
    child = tx_db.get(FamilyMember, form["children"][0]["member_id"])
    assert child.section == "B"
    assert child.academic_year == form["academic_year"]

    history = tx_db.scalars(
        select(FieldHistory).where(FieldHistory.source_reference.like("CEA form%"))
    ).all()
    assert {h.field_name for h in history} >= {"record_office", "bank_ifsc", "section"}


def test_a_blank_box_never_wipes_a_stored_value(client, tx_db):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    form = client.get(f"/api/cea/families/{family_id}/form").json()["form"]
    form["mobile"] = ""
    client.put(f"/api/cea/families/{family_id}/form", json={"form": form})
    assert tx_db.get(Family, family_id).primary_phone == "+919876543210"


def test_a_bad_value_on_the_form_saves_nothing(client, tx_db):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    form = client.get(f"/api/cea/families/{family_id}/form").json()["form"]
    form["mobile"] = "123"
    form["record_office"] = "Should not be saved"
    response = client.put(f"/api/cea/families/{family_id}/form", json={"form": form})
    assert response.status_code == 422
    assert tx_db.get(Family, family_id).record_office is None


def test_the_pdf_is_the_official_pack_with_one_school_page_per_child(client):
    family_id = client.post("/api/families", json=NEW_FAMILY).json()["family_id"]
    form = client.get(f"/api/cea/families/{family_id}/form").json()["form"]
    response = client.post("/api/cea/pdf", json={"form": form})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    pdf = PdfReader(io.BytesIO(response.content))
    # cover, bill (2 pages), self declaration, one school certificate
    assert len(pdf.pages) == 5
    assert "Testa Devi Zzyzx" in pdf.pages[0].extract_text()
