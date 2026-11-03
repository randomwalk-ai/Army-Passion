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
