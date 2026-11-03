"""Voice notes: transcription, filing against a family, and new families.

All rolled back — the development database is left untouched.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import DataQualityIssue, Family, Interaction, VoiceUpload
from app.models.enums import InteractionType, IssueCode
from app.services.speech import MockSpeechToText


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload_audio(client, content: bytes = b"fake audio bytes", name="call.mp3"):
    return client.post(
        "/api/voice/upload", files={"file": (name, content, "audio/mpeg")}
    )


def an_existing_family(session) -> Family:
    family = session.scalars(
        select(Family).where(Family.is_draft.is_(False)).limit(1)
    ).first()
    if family is None:
        pytest.skip("No seeded families — run seed.generate --reset")
    return family


# --- the mock transcriber -----------------------------------------------------


def test_the_same_audio_always_gives_the_same_transcript():
    engine = MockSpeechToText()
    first = engine.transcribe(b"same bytes", "a.mp3")
    second = engine.transcribe(b"same bytes", "b.mp3")
    assert first.text_english == second.text_english


def test_transcription_sends_nothing_and_fills_the_useful_fields():
    result = MockSpeechToText().transcribe(b"audio", "call.mp3")
    assert result.provider == "mock"
    assert result.text_english
    assert result.suggested_fields["summary"]
    assert isinstance(result.suggested_fields["extracted"], dict)


# --- upload -------------------------------------------------------------------


def test_uploading_a_recording_returns_what_was_said(client):
    response = upload_audio(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"]
    assert body["summary"]
    assert body["provider"] == "mock"
    assert body["language"] == "english"


def test_a_file_that_is_not_audio_is_refused(client):
    response = client.post(
        "/api/voice/upload",
        files={"file": ("sheet.xlsx", b"not audio", "application/vnd.ms-excel")},
    )
    assert response.status_code == 400


def test_nothing_is_saved_against_a_family_until_he_confirms(client, tx_db):
    before = tx_db.scalar(
        select(Interaction.id).order_by(Interaction.id.desc()).limit(1)
    )
    upload_audio(client)
    after = tx_db.scalar(
        select(Interaction.id).order_by(Interaction.id.desc()).limit(1)
    )
    assert before == after, "an interaction was created before he confirmed"


# --- filing against a family he already has ----------------------------------


def test_confirming_against_an_existing_family_saves_the_note(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]

    response = client.post(
        f"/api/voice/{voice_id}/confirm", json={"family_id": family.id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_family"] is False
    assert body["family_id"] == family.id

    interaction = tx_db.get(Interaction, body["interaction_id"])
    assert interaction.interaction_type == InteractionType.voice_note
    assert interaction.family_id == family.id
    assert interaction.transcript_english
    assert interaction.audio_storage_key


def test_he_can_correct_the_transcript_before_it_is_saved(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]
    corrected = "He actually said the pension has not arrived."

    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"family_id": family.id, "transcript": corrected},
    ).json()
    assert tx_db.get(Interaction, body["interaction_id"]).transcript_english == corrected


def test_the_same_recording_cannot_be_filed_twice(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]
    assert (
        client.post(f"/api/voice/{voice_id}/confirm", json={"family_id": family.id}).status_code
        == 200
    )
    second = client.post(
        f"/api/voice/{voice_id}/confirm", json={"family_id": family.id}
    )
    assert second.status_code == 409


def test_an_unknown_family_is_refused(client):
    voice_id = upload_audio(client).json()["voice_id"]
    response = client.post(f"/api/voice/{voice_id}/confirm", json={"family_id": 999999})
    assert response.status_code == 404


def test_he_must_choose_exactly_one_of_existing_or_new(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]

    neither = client.post(f"/api/voice/{voice_id}/confirm", json={})
    assert neither.status_code == 400

    both = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"family_id": family.id, "new_family": {"widow_name": "Zzz Both"}},
    )
    assert both.status_code == 400


# --- a family we do not have yet ---------------------------------------------


def test_a_new_family_from_a_voice_note_joins_the_main_list(client, tx_db):
    """Added like any other new family — never a separate 'draft' tier.
    What a call cannot give us becomes a needs-attention item instead."""
    voice_id = upload_audio(client).json()["voice_id"]
    response = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={
            "new_family": {
                "widow_name": "Zzz Kamlesh Devi",
                "soldier_name": "Zzz Ram Kumar",
                "rank": "Havildar",
                "unit": "9 Jat",
                "district": "Rohtak",
                "state": "Haryana",
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_family"] is True
    assert body["is_draft"] is False

    family = tx_db.get(Family, body["family_id"])
    assert family.is_draft is False
    assert family.soldier.full_name == "Zzz Ram Kumar"
    assert any(m.full_name == "Zzz Kamlesh Devi" for m in family.members)


def test_a_new_family_says_what_is_still_missing(client):
    voice_id = upload_audio(client).json()["voice_id"]
    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"new_family": {"widow_name": "Zzz Incomplete", "district": "Rohtak"}},
    ).json()
    missing = body["missing_for_completion"]
    assert "Phone number" in missing
    assert "Date of death" in missing


def test_a_new_family_raises_a_needs_attention_item_per_missing_field(client, tx_db):
    voice_id = upload_audio(client).json()["voice_id"]
    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"new_family": {"widow_name": "Zzz Gapfilled", "district": "Rohtak"}},
    ).json()

    issues = tx_db.scalars(
        select(DataQualityIssue).where(
            DataQualityIssue.family_id == body["family_id"]
        )
    ).all()
    codes = {i.issue_code for i in issues}
    assert IssueCode.missing_phone in codes
    assert IssueCode.missing_date_of_death in codes


def test_a_family_from_a_voice_note_joins_the_main_count(client, tx_db):
    """No separate draft tier: it is a normal family from the moment it is
    saved, found the same way the 150 seeded families are."""
    voice_id = upload_audio(client).json()["voice_id"]
    client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"new_family": {"widow_name": "Zzz Normalfamily"}},
    )
    tx_db.flush()

    found = tx_db.scalars(
        select(Family).where(
            Family.is_draft.is_(False),
            Family.primary_contact_name == "Zzz Normalfamily",
        )
    ).first()
    assert found is not None


def test_a_new_family_needs_at_least_one_name(client):
    voice_id = upload_audio(client).json()["voice_id"]
    response = client.post(
        f"/api/voice/{voice_id}/confirm", json={"new_family": {"district": "Rohtak"}}
    )
    assert response.status_code == 400


def test_bad_values_are_reported_rather_than_silently_dropped(client, tx_db):
    voice_id = upload_audio(client).json()["voice_id"]
    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={
            "new_family": {
                "widow_name": "Zzz Badvalues",
                "phone": "12345",
                "date_of_death": "32-13-2021",
            }
        },
    ).json()
    assert len(body["warnings"]) >= 2
    family = tx_db.get(Family, body["family_id"])
    assert family.primary_phone is None
    assert family.soldier.date_of_death is None


def test_a_new_family_that_looks_like_an_existing_one_is_flagged_not_merged(
    client, tx_db
):
    existing = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]

    body = client.post(
        f"/api/voice/{voice_id}/confirm",
        json={
            "new_family": {
                "widow_name": existing.primary_contact_name,
                "district": existing.district,
            }
        },
    ).json()

    assert body["possible_duplicate_of"] == existing.family_code
    # Both records still exist. Nothing was merged.
    assert tx_db.get(Family, existing.id) is not None
    assert tx_db.get(Family, body["family_id"]) is not None

    flagged = tx_db.scalars(
        select(DataQualityIssue).where(
            DataQualityIssue.family_id == body["family_id"],
            DataQualityIssue.issue_code == IssueCode.possible_duplicate,
        )
    ).all()
    assert flagged


# --- the family picker --------------------------------------------------------


def test_searching_finds_a_family_by_name(client, tx_db):
    family = an_existing_family(tx_db)
    first_name = family.primary_contact_name.split()[0]
    results = client.get(f"/api/families/search?q={first_name}").json()
    assert any(r["family_id"] == family.id for r in results)


def test_searching_finds_a_family_by_its_code(client, tx_db):
    family = an_existing_family(tx_db)
    results = client.get(f"/api/families/search?q={family.family_code}").json()
    assert results[0]["family_code"] == family.family_code


def test_a_family_from_a_voice_note_is_found_by_search_either_way(client, tx_db):
    """It is not a draft, so excluding drafts from a search must not hide it."""
    voice_id = upload_audio(client).json()["voice_id"]
    client.post(
        f"/api/voice/{voice_id}/confirm",
        json={"new_family": {"widow_name": "Zzz Searchnormal"}},
    )
    with_drafts = client.get("/api/families/search?q=Zzz Searchnormal").json()
    without = client.get(
        "/api/families/search?q=Zzz Searchnormal&include_drafts=false"
    ).json()
    assert len(with_drafts) == 1
    assert len(without) == 1


def test_the_voice_upload_is_marked_saved_afterwards(client, tx_db):
    family = an_existing_family(tx_db)
    voice_id = upload_audio(client).json()["voice_id"]
    client.post(f"/api/voice/{voice_id}/confirm", json={"family_id": family.id})
    assert tx_db.get(VoiceUpload, voice_id).status.value == "saved"
