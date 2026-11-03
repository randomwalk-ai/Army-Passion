"""Documents linked to a family, or to one child.

Database writes roll back, and files go to a temporary folder.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import AuditLog, Family
from app.models.enums import Relation

PDF = b"%PDF-1.4 a pretend document"


@pytest.fixture
def client(tx_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def a_family_with_a_child(session) -> tuple[Family, int]:
    for family in session.scalars(select(Family).where(Family.is_draft.is_(False))).all():
        child = next(
            (m for m in family.members if m.relation in (Relation.son, Relation.daughter)),
            None,
        )
        if child:
            return family, child.id
    pytest.skip("No seeded family with a child")


def upload(client, family_id, doc_type="service_booklet", member_id=None,
           name="booklet.pdf", content=PDF):
    data = {"doc_type": doc_type}
    if member_id is not None:
        data["member_id"] = str(member_id)
    return client.post(
        f"/api/families/{family_id}/documents",
        files={"file": (name, content, "application/pdf")},
        data=data,
    )


def test_the_document_types_include_what_the_grant_forms_ask_for(client):
    keys = {t["key"] for t in client.get("/api/document-types").json()}
    for needed in ("service_booklet", "pension_payment_order", "marksheet",
                   "contingent_bill", "self_declaration", "cancelled_cheque"):
        assert needed in keys


def test_members_are_listed_so_he_can_pick_who_a_document_is_for(client, tx_db):
    family, child_id = a_family_with_a_child(tx_db)
    members = client.get(f"/api/families/{family.id}/members").json()
    assert child_id in {m["member_id"] for m in members}


def test_a_document_can_belong_to_the_whole_family(client, tx_db):
    family, _ = a_family_with_a_child(tx_db)
    response = upload(client, family.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["belongs_to"] == "Whole family"
    assert body["member_id"] is None
    assert body["doc_type_label"] == "Service booklet"
    assert body["has_file"] is True


def test_a_document_can_belong_to_one_child(client, tx_db):
    family, child_id = a_family_with_a_child(tx_db)
    body = upload(client, family.id, "marksheet", member_id=child_id, name="marks.pdf").json()
    child_name = next(m.full_name for m in family.members if m.id == child_id)
    assert body["member_id"] == child_id
    assert body["belongs_to"] == child_name


def test_a_person_from_another_family_is_refused(client, tx_db):
    families = tx_db.scalars(select(Family).where(Family.is_draft.is_(False))).all()
    first, second = families[0], families[1]
    stranger = second.members[0].id
    response = upload(client, first.id, "marksheet", member_id=stranger)
    assert response.status_code == 400


def test_only_pdfs_and_photos_are_accepted(client, tx_db):
    family, _ = a_family_with_a_child(tx_db)
    response = upload(client, family.id, name="sheet.xlsx")
    assert response.status_code == 400


def test_an_unknown_document_type_is_refused(client, tx_db):
    family, _ = a_family_with_a_child(tx_db)
    assert upload(client, family.id, doc_type="no_such_type").status_code == 400


def test_an_uploaded_file_can_be_opened_again(client, tx_db):
    family, _ = a_family_with_a_child(tx_db)
    document_id = upload(client, family.id).json()["document_id"]
    response = client.get(f"/api/documents/{document_id}/file")
    assert response.status_code == 200
    assert response.content == PDF


def test_a_familys_documents_are_listed(client, tx_db):
    family, child_id = a_family_with_a_child(tx_db)
    upload(client, family.id)
    upload(client, family.id, "marksheet", member_id=child_id, name="m.pdf")
    listed = client.get(f"/api/families/{family.id}/documents").json()
    uploaded = [d for d in listed if d["has_file"]]
    assert {d["doc_type"] for d in uploaded} >= {"service_booklet", "marksheet"}


def test_a_mistaken_upload_can_be_deleted_and_the_deletion_is_logged(client, tx_db):
    family, _ = a_family_with_a_child(tx_db)
    document_id = upload(client, family.id).json()["document_id"]

    assert client.delete(f"/api/documents/{document_id}").status_code == 200
    assert client.get(f"/api/documents/{document_id}/file").status_code == 404

    logged = tx_db.scalars(
        select(AuditLog).where(
            AuditLog.action == "document.delete", AuditLog.entity_id == family.id
        )
    ).all()
    assert logged


def test_a_mock_record_without_a_file_says_so(client, tx_db):
    """The seeded documents are records only; there is no file behind them."""
    family, _ = a_family_with_a_child(tx_db)
    seeded = [d for d in client.get(f"/api/families/{family.id}/documents").json()
              if not d["has_file"]]
    if not seeded:
        pytest.skip("This family has no seeded document records")
    response = client.get(f"/api/documents/{seeded[0]['document_id']}/file")
    assert response.status_code == 404
    assert "mock" in response.json()["detail"]
