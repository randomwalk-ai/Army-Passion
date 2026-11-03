"""The LLM reading a voice transcript: who is it about, what changed.

The rule being protected: a suggestion is only ever a suggestion. Nothing
reaches the database until the colonel explicitly agrees to it, field by
field, and every applied change says the call is the source.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import Family, FieldHistory
from app.models.enums import ChangeSource
from app.services.llm import (
    MockTranscriptLLM,
    TRANSCRIPT_EDITABLE_FIELDS,
    build_transcript_prompt,
    parse_transcript_response,
)


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


FIELDS = TRANSCRIPT_EDITABLE_FIELDS
CANDIDATES = [
    (1, "AP-2026-0001", "Sunita Devi", "Hisar"),
    (2, "AP-2026-0002", "Kamlesh Devi", "Rohtak"),
]


# --- privacy --------------------------------------------------------------


def test_the_prompt_only_contains_the_transcript_and_candidate_names():
    prompt = build_transcript_prompt("Hello, this is about Kamlesh Devi.", CANDIDATES)
    assert "Kamlesh Devi" in prompt
    assert "Sunita Devi" in prompt
    # Fields that must never be proposed are never even mentioned.
    for forbidden in ("bank_account_number", "bank_ifsc", "annual_income"):
        assert forbidden not in prompt


def test_only_a_short_safe_list_of_fields_can_be_proposed():
    keys = {k for k, _ in FIELDS}
    assert keys == {"phone", "alternate_phone", "village_or_town", "district", "state"}
    assert "bank_account_number" not in keys


# --- the fake ---------------------------------------------------------------


def test_the_fake_finds_a_name_mentioned_in_the_transcript():
    result = MockTranscriptLLM().analyse_transcript(
        "Hello sir, this is about Kamlesh Devi from Rohtak.", CANDIDATES
    )
    assert result.family_guess is not None
    assert result.family_guess.family_code == "AP-2026-0002"


def test_the_fake_finds_nothing_when_no_name_matches():
    result = MockTranscriptLLM().analyse_transcript(
        "Everything is fine, no changes.", CANDIDATES
    )
    assert result.family_guess is None


def test_the_fake_never_proposes_field_changes():
    """The fake exists to test the family-matching wiring; real field
    extraction is a real-LLM job, not something to fake convincingly."""
    result = MockTranscriptLLM().analyse_transcript(
        "This is about Kamlesh Devi, her phone number has changed.", CANDIDATES
    )
    assert result.field_changes == []


# --- reading a model's reply -------------------------------------------------


def test_a_well_formed_reply_is_read_correctly():
    text = """{"family": {"id": 2, "confidence": 85, "reason": "name matches"},
                "changes": [{"field_key": "phone", "new_value": "9876543210",
                             "reason": "she gave a new number"}]}"""
    result = parse_transcript_response(text, CANDIDATES)
    assert result.family_guess.family_code == "AP-2026-0002"
    assert result.field_changes[0].field_key == "phone"
    assert result.field_changes[0].new_value == "9876543210"


def test_a_family_id_outside_the_candidate_list_is_rejected():
    """The LLM must never point at a family it was not shown."""
    text = '{"family": {"id": 999, "confidence": 90}, "changes": []}'
    result = parse_transcript_response(text, CANDIDATES)
    assert result.family_guess is None


def test_a_field_key_outside_the_allowed_list_is_dropped():
    text = """{"family": {"id": null}, "changes": [
        {"field_key": "bank_account_number", "new_value": "123456"}]}"""
    result = parse_transcript_response(text, CANDIDATES)
    assert result.field_changes == []


def test_nonsense_is_ignored_rather_than_crashing():
    result = parse_transcript_response("not json at all", CANDIDATES)
    assert result.family_guess is None
    assert result.field_changes == []


# --- applying a confirmed change through the API -----------------------------


def an_existing_family(session) -> Family:
    family = session.scalars(select(Family).where(Family.is_draft.is_(False))).first()
    if family is None:
        pytest.skip("No seeded families — run seed.generate --reset")
    return family


def upload_audio(client, content=b"fake audio", name="call.mp3"):
    return client.post("/api/voice/upload", files={"file": (name, content, "audio/mpeg")})


def test_an_unconfirmed_suggestion_changes_nothing(client, tx_db):
    """Uploading alone must never write to a family's fields."""
    family = an_existing_family(tx_db)
    before_phone = family.primary_phone

    voice_id = upload_audio(client).json()["voice_id"]
    client.post(f"/api/voice/{voice_id}/confirm", json={"family_id": family.id})

    tx_db.expire_all()
    assert tx_db.get(Family, family.id).primary_phone == before_phone


def test_confirming_a_field_change_writes_it_with_history(client, tx_db, monkeypatch):
    """Simulates the LLM having proposed a phone change, then the colonel
    agreeing to it — the part a real Gemini call cannot be tested with here."""
    family = an_existing_family(tx_db)

    voice_id = upload_audio(client).json()["voice_id"]

    from app.models import VoiceUpload

    upload = tx_db.get(VoiceUpload, voice_id)
    upload.suggested_fields = {
        **upload.suggested_fields,
        "llm_field_changes": [
            {
                "field_key": "phone",
                "label": "Phone number",
                "new_value": "9876500001",
                "reason": "She gave a new number on the call",
            }
        ],
    }
    tx_db.commit()

    response = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"family_id": family.id, "apply_field_changes": ["phone"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "primary_phone" in body["fields_updated"]

    tx_db.expire_all()
    updated = tx_db.get(Family, family.id)
    assert updated.primary_phone == "+919876500001"

    history = tx_db.scalars(
        select(FieldHistory)
        .where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "primary_phone",
        )
        .order_by(FieldHistory.id.desc())
    ).first()
    assert history.source == ChangeSource.voice_note
    assert history.new_value == "+919876500001"


def test_a_bad_proposed_phone_is_not_applied(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]

    from app.models import VoiceUpload

    upload = tx_db.get(VoiceUpload, voice_id)
    upload.suggested_fields = {
        **upload.suggested_fields,
        "llm_field_changes": [
            {"field_key": "phone", "label": "Phone number", "new_value": "12345", "reason": ""}
        ],
    }
    tx_db.commit()

    before_phone = family.primary_phone
    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"family_id": family.id, "apply_field_changes": ["phone"]},
    ).json()

    assert body["fields_updated"] == []
    assert body["warnings"], "a rejected suggestion should say why"
    tx_db.expire_all()
    assert tx_db.get(Family, family.id).primary_phone == before_phone


def test_field_changes_are_not_applied_to_a_brand_new_family(client):
    """apply_field_changes only makes sense against a family that already has
    the field — a new draft has nothing to update."""
    voice_id = upload_audio(client).json()["voice_id"]
    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={
            "new_family": {"widow_name": "Zzz Newfieldtest"},
            "apply_field_changes": ["phone"],
        },
    ).json()
    assert body["fields_updated"] == []
