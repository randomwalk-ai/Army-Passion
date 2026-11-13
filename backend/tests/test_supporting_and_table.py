"""Supporting documents (1 to 4 per family), attaching them to the CEA PDF,
and the editable families table.

Database writes roll back, and files go to a temporary folder.
"""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Family, FieldHistory
from app.services.document_pack import Attachment, append_documents
from app.services.storage import S3Storage


def one_page_pdf(text="test") -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(100, 700, text)
    c.save()
    return buffer.getvalue()


def png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client(tx_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def a_family_without_documents(session) -> Family:
    for family in session.scalars(
        select(Family).where(Family.is_draft.is_(False)).order_by(Family.id)
    ).all():
        if not any(d.is_supporting for d in family.documents):
            return family
    pytest.skip("Every seeded family already has supporting documents")


def first_family(session) -> Family:
    return session.scalars(
        select(Family).where(Family.is_draft.is_(False)).order_by(Family.id)
    ).first()


def add(client, family_id, name="ppo.pdf", content=None, doc_type="pension_payment_order"):
    return client.post(
        f"/api/families/{family_id}/supporting-documents",
        files={"file": (name, content or one_page_pdf(), "application/pdf")},
        data={"doc_type": doc_type},
    )


# --- supporting documents ------------------------------------------------------


def test_a_family_can_have_up_to_four_documents_and_no_more(client, tx_db):
    family = a_family_without_documents(tx_db)
    for n in range(4):
        response = add(client, family.id, name=f"doc{n}.pdf")
        assert response.status_code == 200, response.text
    body = response.json()
    assert (body["minimum"], body["maximum"], len(body["documents"])) == (1, 4, 4)

    fifth = add(client, family.id, name="doc5.pdf")
    assert fifth.status_code == 409
    assert "Remove one first" in fifth.json()["detail"]


def test_the_last_document_cannot_be_removed(client, tx_db):
    family = a_family_without_documents(tx_db)
    first = add(client, family.id).json()["documents"][0]["document_id"]
    refused = client.delete(f"/api/families/{family.id}/supporting-documents/{first}")
    assert refused.status_code == 409

    add(client, family.id, name="second.pdf")
    removed = client.delete(f"/api/families/{family.id}/supporting-documents/{first}")
    assert removed.status_code == 200
    assert [d["filename"] for d in removed.json()["documents"]] == ["second.pdf"]


def test_only_pdfs_and_photos_are_taken(client, tx_db):
    family = a_family_without_documents(tx_db)
    response = client.post(
        f"/api/families/{family.id}/supporting-documents",
        files={"file": ("notes.docx", b"PK..", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_blob_storage_says_plainly_that_it_is_not_connected(monkeypatch):
    monkeypatch.setattr(settings, "s3_bucket", "")
    with pytest.raises(NotImplementedError, match="S3_BUCKET"):
        S3Storage()


# --- attaching them to the CEA pack ---------------------------------------------


def test_documents_are_added_after_the_form_pages():
    out = append_documents(one_page_pdf("form"), [
        Attachment("PPO", "ppo.pdf", "application/pdf", one_page_pdf("ppo")),
        Attachment("Aadhaar card", "aadhaar.png", "image/png", png()),
    ])
    pages = PdfReader(io.BytesIO(out)).pages
    assert len(pages) == 3
    assert "form" in pages[0].extract_text()
    assert "ppo" in pages[1].extract_text()
    assert "Supporting document 2 of 2" in pages[2].extract_text()


def test_a_broken_or_missing_file_leaves_a_note_instead_of_failing():
    out = append_documents(one_page_pdf("form"), [
        Attachment("PPO", "ppo.pdf", "application/pdf", b"not really a pdf"),
        Attachment("Passbook", "passbook.pdf", "application/pdf", None),
    ])
    pages = PdfReader(io.BytesIO(out)).pages
    assert len(pages) == 3
    assert "print it separately" in pages[1].extract_text()
    assert "could not be found" in pages[2].extract_text()


def test_the_cea_pdf_can_include_the_familys_documents(client, tx_db):
    family = a_family_without_documents(tx_db)
    add(client, family.id)
    add(client, family.id, name="photo.png", content=png(), doc_type="aadhaar")
    form = client.get(f"/api/cea/families/{family.id}/form").json()["form"]

    plain = client.post("/api/cea/pdf", json={"form": form})
    with_documents = client.post("/api/cea/pdf", json={"form": form, "include_documents": True})
    assert plain.status_code == with_documents.status_code == 200
    extra = len(PdfReader(io.BytesIO(with_documents.content)).pages) - len(
        PdfReader(io.BytesIO(plain.content)).pages
    )
    assert extra == 2


# --- the families table ---------------------------------------------------------


def test_the_table_lists_families_page_by_page(client):
    body = client.get("/api/families/table?page_size=10").json()
    assert len(body["rows"]) == 10
    assert body["total"] >= 100
    keys = [c["key"] for c in body["columns"]]
    assert keys[0] == "primary_contact_name"
    assert {"documents", "primary_phone", "date_of_death"} <= set(keys)
    assert not next(c for c in body["columns"] if c["key"] == "documents")["editable"]


def test_the_no_documents_filter_only_shows_families_without_any(client):
    body = client.get("/api/families/table?filter=no_documents&page_size=100").json()
    assert body["rows"]
    assert all(r["values"]["documents"] == 0 for r in body["rows"])
    counts = {f["key"]: f["count"] for f in body["filters"]}
    assert counts["no_documents"] == body["total"] < counts["all"]


def test_searching_finds_a_family_by_soldier_name(client, tx_db):
    family = first_family(tx_db)
    first_name = family.soldier.full_name.split()[0]
    rows = client.get(f"/api/families/table?q={first_name}&page_size=100").json()["rows"]
    assert family.id in {r["family_id"] for r in rows}


def test_editing_a_cell_cleans_the_value_and_keeps_the_old_one(client, tx_db):
    family = first_family(tx_db)
    old = family.primary_phone
    response = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "primary_phone", "value": "98765 43210"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["row"]["values"]["primary_phone"] == "+919876543210"

    history = tx_db.scalars(
        select(FieldHistory)
        .where(FieldHistory.entity_id == family.id, FieldHistory.field_name == "primary_phone")
        .order_by(FieldHistory.id.desc())
    ).first()
    assert (history.old_value, history.new_value) == (old, "+919876543210")


def test_a_soldier_date_is_read_day_first(client, tx_db):
    family = first_family(tx_db)
    response = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "date_of_death", "value": "05/03/2024"}
    )
    assert response.json()["row"]["values"]["date_of_death"] == "05-03-2024"


@pytest.mark.parametrize(
    "key, value, says",
    [
        ("primary_phone", "12345", "10-digit"),
        ("primary_contact_name", "", "cannot be left empty"),
        ("documents", "3", "cannot be changed"),
        ("family_code", "X", "cannot be changed"),
        ("preferred_language", "klingon", "not one of the languages"),
    ],
)
def test_bad_edits_are_refused_in_plain_words(client, tx_db, key, value, says):
    family = first_family(tx_db)
    response = client.patch(f"/api/families/{family.id}/cell", json={"key": key, "value": value})
    assert response.status_code == 422
    assert says in response.json()["detail"]


def test_an_unchanged_value_writes_no_history(client, tx_db):
    family = first_family(tx_db)
    before = tx_db.query(FieldHistory).count()
    response = client.patch(
        f"/api/families/{family.id}/cell",
        json={"key": "district", "value": f"  {family.district}  "},
    )
    assert response.json()["changed"] is False
    assert tx_db.query(FieldHistory).count() == before


def test_the_dashboard_counts_families_without_documents(client):
    stats = {s["key"]: s for s in client.get("/api/dashboard").json()["stats"]}
    assert stats["no_documents"]["value"] > 0


def test_one_family_can_be_fetched_as_a_row(client, tx_db):
    family = first_family(tx_db)
    body = client.get(f"/api/families/{family.id}/row").json()
    assert body["family_id"] == family.id
    assert body["values"]["family_code"] == family.family_code
    assert client.get("/api/families/999999/row").status_code == 404


# --- every detail is a column -------------------------------------------------


def family_with_children(session, count: int) -> Family:
    from app.services.family_table import children_of

    for family in session.scalars(
        select(Family).where(Family.is_draft.is_(False)).order_by(Family.id)
    ):
        if len(children_of(family)) == count:
            return family
    pytest.skip(f"no family with {count} children in the seed data")


def test_the_table_has_every_detail_the_database_holds(client):
    keys = {c["key"] for c in client.get("/api/families/table?page_size=1").json()["columns"]}
    for key in (
        "tehsil", "post_office", "gps_coordinates", "regiment", "cause_of_death",
        "bank_branch", "co_unit_phone", "record_office", "correspondence_pincode",
        "annual_income", "notes", "child1_name", "child3_marital_status",
    ):
        assert key in keys


def test_child_one_is_the_oldest(client, tx_db):
    from app.services.family_table import children_of

    family = family_with_children(tx_db, 2)
    oldest = children_of(family)[0]
    values = client.get(f"/api/families/{family.id}/row").json()["values"]
    assert values["child1_name"] == oldest.full_name


def test_a_name_in_the_next_empty_child_adds_that_child(client, tx_db):
    family = family_with_children(tx_db, 1)
    response = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "child2_name", "value": "PRIYA DEVI"}
    )
    assert response.status_code == 200, response.text
    values = response.json()["row"]["values"]
    assert values["children"] == 2
    assert "Priya Devi" in (values["child1_name"], values["child2_name"])


@pytest.mark.parametrize(
    "key, value, says",
    [
        ("child3_name", "Ravi", "Add Child 2 first"),
        ("child2_sex", "M", "name first"),
        ("child1_name", "", "cannot be left empty"),
        ("child1_sex", "X", "M or F"),
    ],
)
def test_bad_child_edits_are_refused(client, tx_db, key, value, says):
    family = family_with_children(tx_db, 1)
    response = client.patch(f"/api/families/{family.id}/cell", json={"key": key, "value": value})
    assert response.status_code == 422
    assert says in response.json()["detail"]


def test_a_childs_sex_makes_them_a_son_or_daughter(client, tx_db):
    from app.services.family_table import children_of

    family = family_with_children(tx_db, 1)
    client.patch(f"/api/families/{family.id}/cell", json={"key": "child1_sex", "value": "F"})
    tx_db.expire_all()
    assert children_of(tx_db.get(Family, family.id))[0].relation.value == "daughter"


def test_cause_of_death_is_filed_under_a_category(client, tx_db):
    family = first_family(tx_db)
    response = client.patch(
        f"/api/families/{family.id}/cell",
        json={"key": "cause_of_death", "value": "Road accident on NH-44"},
    )
    assert response.json()["row"]["values"]["cause_of_death"] == "Road accident on NH-44"
    tx_db.expire_all()
    assert tx_db.get(Family, family.id).soldier.cause_category.value == "accident"


def test_gps_is_checked_and_tidied(client, tx_db):
    family = first_family(tx_db)
    response = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "gps_coordinates", "value": "28.6139 77.209"}
    )
    assert response.json()["row"]["values"]["gps_coordinates"] == "28.613900, 77.209000"
    bad = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "gps_coordinates", "value": "hello"}
    )
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "key, value, shown",
    [
        ("duty_status", "on leave", "on leave"),
        ("nok_is_govt_servant", "no", "No"),
        ("whatsapp_opted_in", "Yes", "Yes"),
        ("soldier_dob", "1-2-1985", "01-02-1985"),
        ("child1_current_class", "Class 9", "Class 9"),
        ("child1_is_hostel", "yes", "Yes"),
        ("child1_aadhaar_last4", "xxxx xxxx 1234", "1234"),
    ],
)
def test_form_fields_are_columns_too(client, tx_db, key, value, shown):
    family = family_with_children(tx_db, 1)
    response = client.patch(f"/api/families/{family.id}/cell", json={"key": key, "value": value})
    assert response.status_code == 200, response.text
    assert response.json()["row"]["values"][key] == shown


@pytest.mark.parametrize(
    "key, value, says",
    [
        ("duty_status", "", "cannot be left empty"),
        ("nok_is_govt_servant", "maybe", "Yes or No"),
        ("child1_aadhaar_last4", "123", "last 4 digits"),
    ],
)
def test_bad_form_values_are_refused(client, tx_db, key, value, says):
    family = family_with_children(tx_db, 1)
    response = client.patch(f"/api/families/{family.id}/cell", json={"key": key, "value": value})
    assert response.status_code == 422
    assert says in response.json()["detail"]


# --- profile completeness -----------------------------------------------------


def test_every_row_has_a_profile_percentage_and_what_is_missing(client):
    rows = client.get("/api/families/table?page_size=20").json()["rows"]
    for r in rows:
        percent = r["values"]["profile"]
        assert 0 <= percent <= 100
        assert (percent == 100) == (r["missing"] == [])


def test_filling_a_missing_detail_raises_the_percentage(client, tx_db):
    family = first_family(tx_db)
    before = client.get(f"/api/families/{family.id}/row").json()
    assert "Tehsil" in before["missing"] or family.tehsil
    client.patch(f"/api/families/{family.id}/cell", json={"key": "tehsil", "value": ""})
    emptied = client.get(f"/api/families/{family.id}/row").json()
    filled = client.patch(
        f"/api/families/{family.id}/cell", json={"key": "tehsil", "value": "Vikasnagar"}
    ).json()["row"]
    assert filled["values"]["profile"] > emptied["values"]["profile"]
    assert "Tehsil" not in filled["missing"]


def test_a_missing_childs_details_are_not_counted(tx_db):
    from app.services.family_table import columns, completeness

    family = family_with_children(tx_db, 1)
    _, missing = completeness(family, columns(tx_db), 1)
    assert not any(label.startswith(("Child 2", "Child 3")) for label in missing)


def test_sorting_by_profile_puts_the_least_complete_first_across_pages(client):
    first = client.get("/api/families/table?sort=profile&page=1&page_size=10").json()
    second = client.get("/api/families/table?sort=profile&page=2&page_size=10").json()
    percents = [r["values"]["profile"] for r in first["rows"] + second["rows"]]
    assert percents == sorted(percents)
    top = client.get("/api/families/table?sort=profile&descending=true&page_size=5").json()
    assert top["rows"][0]["values"]["profile"] >= percents[-1]


def test_the_profile_spread_adds_up_to_every_family(client):
    spread = client.get("/api/families/profile-spread").json()
    assert len(spread["counts"]) == 101
    assert sum(spread["counts"]) == spread["total"] > 0
    assert 0 <= spread["average"] <= 100
    assert spread["spread"] >= 0
