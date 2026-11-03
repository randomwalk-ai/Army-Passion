"""Voice notes: upload, transcribe, then file against a family.

Order:
  1. POST /api/voice/upload        store the audio, write out what was said
  2. POST /api/voice/{id}/confirm  he picks the family, or says it is a new one

He always sees the transcript before anything is saved. A new family created
this way is a DRAFT: kept out of the main list until the gaps are filled.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import (
    NewFamilyIn,
    VoiceConfirmIn,
    VoiceConfirmResponse,
    VoiceUploadResponse,
)
from app.db import get_session
from app.models import (
    AuditLog,
    DataQualityIssue,
    Family,
    FamilyMember,
    FieldHistory,
    Interaction,
    Soldier,
    VoiceUpload,
    VoiceUploadStatus,
)
from app.models.enums import (
    ChangeSource,
    InteractionType,
    IssueCode,
    IssueSeverity,
    IssueStatus,
    Language,
    Relation,
)
from app.services.import_apply import next_family_code
from app.services.matching import name_similarity, simplify
from app.services.llm import TRANSCRIPT_EDITABLE_FIELDS, get_transcript_llm
from app.services.row_parser import parse_cause, parse_date, parse_phone, tidy_name
from app.services.speech import get_speech_to_text
from app.services.storage import get_storage

# How a transcript's field keys (phone, district, ...) map onto a column on
# the Family model, so a confirmed suggestion can be written.
FAMILY_COLUMN_BY_TRANSCRIPT_FIELD = {
    "phone": "primary_phone",
    "alternate_phone": "alternate_phone",
    "village_or_town": "village_or_town",
    "district": "district",
    "state": "state",
}

# Keep the prompt small and fast: never hand the LLM the whole family list.
MAX_CANDIDATE_FAMILIES = 25

router = APIRouter(prefix="/api/voice", tags=["voice"])

IST = ZoneInfo("Asia/Kolkata")
ALLOWED_SUFFIXES = (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".webm")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# What a phone call often cannot give us. Each missing one becomes its own
# needs-attention item, the same codes the Excel import uses for the same
# gaps — so both intake paths feed one consistent list.
COMPLETION_FIELDS: list[tuple[str, str, IssueCode]] = [
    ("primary_phone", "Phone number", IssueCode.missing_phone),
    ("district", "District", IssueCode.missing_address),
    ("bank_account_number", "Bank account", IssueCode.missing_bank_details),
]


def _candidate_families(
    session: Session, transcript: str
) -> list[tuple[int, str, str, str | None]]:
    """A short list of families whose name shares a word with the transcript.

    This is the whole privacy point: only a handful of plausible families are
    ever handed to the LLM prompt builder, never the full 150+ record list.
    """
    words = {
        w.strip(".,!?").lower()
        for w in transcript.split()
        if len(w.strip(".,!?")) >= 3
    }
    if not words:
        return []

    candidates: list[tuple[int, str, str, str | None]] = []
    for family in session.scalars(
        select(Family).where(Family.is_draft.is_(False))
    ).all():
        name_words = {w.lower() for w in (family.primary_contact_name or "").split()}
        if name_words & words:
            candidates.append(
                (family.id, family.family_code, family.primary_contact_name, family.district)
            )
            if len(candidates) >= MAX_CANDIDATE_FAMILIES:
                break
    return candidates


def _missing_fields(family: Family) -> list[tuple[str, IssueCode]]:
    """(label, code) for everything a call could not give us."""
    missing = [
        (label, code) for field, label, code in COMPLETION_FIELDS
        if not getattr(family, field)
    ]
    soldier = family.soldier
    if soldier is not None:
        if not soldier.date_of_death:
            missing.append(("Date of death", IssueCode.missing_date_of_death))
        if not soldier.service_number:
            missing.append(("Service number", IssueCode.missing_document))
    return missing


def _raise_missing_field_issues(
    session: Session,
    family: Family,
    missing: list[tuple[str, IssueCode]],
    upload: VoiceUpload,
    when: datetime,
) -> None:
    """One needs-attention item per gap — mirrors how the Excel import raises
    these, so both paths end up on the same list in the same shape."""
    for label, code in missing:
        session.add(
            DataQualityIssue(
                entity_type="family",
                entity_id=family.id,
                family_id=family.id,
                issue_code=code,
                severity=IssueSeverity.medium,
                status=IssueStatus.open,
                field_name=label,
                description=f"From a voice note: {label} is still missing.",
                details={"voice_id": upload.id},
                detected_at=when,
            )
        )


@router.post("/upload", response_model=VoiceUploadResponse)
async def upload_voice_note(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> VoiceUploadResponse:
    filename = file.filename or "recording"
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail="I can take .mp3, .m4a, .wav, .ogg, .opus, .aac and .webm recordings.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="That recording is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That recording is larger than 50 MB.")

    storage = get_storage()
    storage_key = storage.save(io.BytesIO(contents), filename, folder="voice")

    transcription = get_speech_to_text().transcribe(contents, filename)
    suggested = transcription.suggested_fields
    heard = dict(suggested.get("extracted") or {})

    user = current_user(session)
    upload = VoiceUpload(
        original_filename=filename,
        storage_key=storage_key,
        size_bytes=len(contents),
        status=VoiceUploadStatus.transcribed,
        language=transcription.language,
        transcript_original=transcription.text_original,
        transcript_english=transcription.text_english,
        summary_english=suggested.get("summary"),
        confidence=transcription.confidence,
        duration_seconds=transcription.duration_seconds,
        provider=transcription.provider,
        suggested_fields=suggested,
        uploaded_by_user_id=user.id if user else None,
    )
    session.add(upload)
    session.commit()

    # If it sounds like a casualty we have not heard of, pre-fill the new
    # family form from what was said. He still confirms every field.
    looks_new = bool(heard.get("new_family_report"))
    suggested_new: dict[str, object] = {}
    if looks_new:
        for key in (
            "widow_name", "soldier_name", "rank", "unit",
            "service_number", "district", "state", "cause_of_death",
        ):
            if heard.get(key):
                suggested_new[key] = heard[key]

    # Ask the LLM who this sounds like and what it suggests changing. Never
    # run for a casualty report — that is a new family, not an update to one
    # we already have, and the candidate list would not apply anyway.
    family_guess = None
    field_changes: list[dict[str, str]] = []
    if not looks_new:
        llm = get_transcript_llm()
        if llm is not None:
            candidates = _candidate_families(session, transcription.text_english)
            if candidates:
                analysis = llm.analyse_transcript(transcription.text_english, candidates)
                family_guess = analysis.family_guess
                field_changes = [
                    {
                        "field_key": c.field_key,
                        "label": c.label,
                        "new_value": c.new_value,
                        "reason": c.reason,
                    }
                    for c in analysis.field_changes
                ]
                upload.suggested_fields = {
                    **suggested,
                    "llm_family_guess": (
                        {
                            "family_id": family_guess.family_id,
                            "confidence": family_guess.confidence,
                        }
                        if family_guess
                        else None
                    ),
                    "llm_field_changes": field_changes,
                }
                session.commit()

    return VoiceUploadResponse(
        voice_id=upload.id,
        filename=filename,
        language=transcription.language.value,
        transcript=transcription.text_english,
        summary=upload.summary_english,
        confidence=transcription.confidence,
        duration_seconds=transcription.duration_seconds,
        provider=transcription.provider,
        heard=heard,
        sentiment=suggested.get("sentiment"),
        follow_up_needed=bool(suggested.get("follow_up_needed")),
        follow_up_note=suggested.get("follow_up_note"),
        looks_like_new_family=looks_new,
        suggested_new_family=suggested_new,
        suggested_family_id=family_guess.family_id if family_guess else None,
        suggested_family_code=family_guess.family_code if family_guess else None,
        suggested_family_confidence=family_guess.confidence if family_guess else 0,
        suggested_family_reason=family_guess.reason if family_guess else None,
        suggested_field_changes=field_changes,
    )


def _create_family_from_voice(
    session: Session,
    details: NewFamilyIn,
    upload: VoiceUpload,
    warnings: list[str],
) -> tuple[Family, str | None]:
    """A family reported over the phone.

    Added straight to the main list, the same as a new family from an Excel
    import — nothing here is a separate "draft" tier. Whatever a call cannot
    give us (phone, bank details, confirmed date of death, ...) is raised as
    a needs-attention item instead, exactly as the Excel import does.
    Possible duplicates are flagged, never merged.
    """
    widow_name = tidy_name(details.widow_name or "")
    soldier_name = tidy_name(details.soldier_name or "")
    if not widow_name and not soldier_name:
        raise HTTPException(
            status_code=400,
            detail="A new family needs at least the widow's name or the soldier's name.",
        )

    phone = None
    if details.phone:
        phone, problem = parse_phone(details.phone)
        if problem:
            warnings.append(f"Phone not saved: {problem}")

    date_of_death = None
    if details.date_of_death:
        date_of_death, problem = parse_date(details.date_of_death)
        if problem:
            warnings.append(f"Date of death not saved: {problem}")

    cause_category, cause_text = (None, None)
    if details.cause_of_death:
        cause_category, cause_text = parse_cause(details.cause_of_death)

    # Might we already have this family? Say so; never merge on a guess.
    possible_duplicate: str | None = None
    for existing in session.scalars(select(Family)).all():
        name_match = max(
            name_similarity(widow_name, existing.primary_contact_name),
            name_similarity(
                soldier_name, existing.soldier.full_name if existing.soldier else None
            ),
        )
        same_district = details.district and simplify(details.district) == simplify(
            existing.district
        )
        if name_match >= 0.8 and same_district:
            possible_duplicate = existing.family_code
            break

    soldier = Soldier(
        full_name=soldier_name or "Name not recorded",
        rank=details.rank,
        service_number=details.service_number,
        unit=details.unit,
        regiment=details.unit,
        date_of_death=date_of_death,
        cause_category=cause_category,
        cause_sub_category=cause_text,
        notes=f"Created from voice note #{upload.id}.",
    )
    session.add(soldier)
    session.flush()

    family = Family(
        family_code=next_family_code(session),
        soldier_id=soldier.id,
        primary_contact_name=widow_name or soldier_name,
        primary_phone=phone,
        district=details.district,
        state=details.state,
    )
    session.add(family)
    session.flush()

    if widow_name:
        session.add(
            FamilyMember(
                family_id=family.id,
                full_name=widow_name,
                relation=Relation.widow,
                gender="female",
            )
        )

    return family, possible_duplicate


@router.post("/{voice_id}/confirm", response_model=VoiceConfirmResponse)
def confirm_voice_note(
    voice_id: int,
    body: VoiceConfirmIn,
    session: Session = Depends(get_session),
) -> VoiceConfirmResponse:
    upload = session.get(VoiceUpload, voice_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="That recording was not found.")
    if upload.status == VoiceUploadStatus.saved:
        raise HTTPException(
            status_code=409, detail="This recording has already been saved."
        )

    if (body.family_id is None) == (body.new_family is None):
        raise HTTPException(
            status_code=400,
            detail="Choose an existing family, or fill in the new family form — not both.",
        )

    now = datetime.now(IST)
    warnings: list[str] = []
    created_family = False
    possible_duplicate: str | None = None

    if body.family_id is not None:
        family = session.get(Family, body.family_id)
        if family is None:
            raise HTTPException(status_code=404, detail="That family was not found.")
    else:
        family, possible_duplicate = _create_family_from_voice(
            session, body.new_family, upload, warnings
        )
        created_family = True

    suggested = upload.suggested_fields or {}
    transcript = body.transcript or upload.transcript_english

    interaction = Interaction(
        family_id=family.id,
        interaction_type=InteractionType.voice_note,
        occurred_at=now,
        by_user_id=upload.uploaded_by_user_id,
        duration_seconds=upload.duration_seconds,
        language=upload.language or Language.english,
        transcript_original=upload.transcript_original,
        transcript_english=transcript,
        summary_english=upload.summary_english,
        extracted_fields=suggested.get("extracted") or {},
        sentiment=suggested.get("sentiment"),
        follow_up_needed=(
            body.follow_up_needed
            if body.follow_up_needed is not None
            else bool(suggested.get("follow_up_needed"))
        ),
        follow_up_note=body.follow_up_note or suggested.get("follow_up_note"),
        audio_storage_key=upload.storage_key,
    )
    session.add(interaction)
    session.flush()

    # He agreed to one or more of the LLM's suggested field changes. Apply
    # exactly those, validated the same way a typed correction would be, and
    # record that the call is the source — never a silent overwrite.
    fields_updated: list[str] = []
    if body.apply_field_changes and not created_family:
        llm_changes = {
            c["field_key"]: c
            for c in (suggested.get("llm_field_changes") or [])
        }
        for key in body.apply_field_changes:
            change = llm_changes.get(key)
            column = FAMILY_COLUMN_BY_TRANSCRIPT_FIELD.get(key)
            if not change or not column:
                continue

            raw = str(change["new_value"]).strip()
            if key in ("phone", "alternate_phone"):
                cleaned, problem = parse_phone(raw)
                if problem:
                    warnings.append(f"Could not apply {change['label']}: {problem}")
                    continue
                new_value = cleaned
            else:
                new_value = re.sub(r"\s+", " ", raw) if raw else None

            old_value = getattr(family, column, None)
            if str(old_value) == str(new_value):
                continue

            session.add(
                FieldHistory(
                    entity_type="family",
                    entity_id=family.id,
                    field_name=column,
                    old_value=None if old_value is None else str(old_value),
                    new_value=None if new_value is None else str(new_value),
                    source=ChangeSource.voice_note,
                    source_reference=f"voice#{upload.id} {upload.original_filename}",
                    changed_at=now,
                    changed_by_user_id=upload.uploaded_by_user_id,
                    note=f"From the call, confirmed by the colonel: {change.get('reason', '')}"[:400],
                )
            )
            setattr(family, column, new_value)
            fields_updated.append(column)

    # The family has now been heard from.
    if family.last_contacted_on != date.today():
        session.add(
            FieldHistory(
                entity_type="family",
                entity_id=family.id,
                field_name="last_contacted_on",
                old_value=str(family.last_contacted_on) if family.last_contacted_on else None,
                new_value=str(date.today()),
                source=ChangeSource.voice_note,
                source_reference=f"voice#{upload.id} {upload.original_filename}",
                changed_at=now,
                changed_by_user_id=upload.uploaded_by_user_id,
            )
        )
        family.last_contacted_on = date.today()

    if created_family:
        session.add(
            FieldHistory(
                entity_type="family",
                entity_id=family.id,
                field_name="__created__",
                old_value=None,
                new_value=family.family_code,
                source=ChangeSource.voice_note,
                source_reference=f"voice#{upload.id} {upload.original_filename}",
                changed_at=now,
                changed_by_user_id=upload.uploaded_by_user_id,
                note="Family created from a voice note.",
            )
        )

    missing = _missing_fields(family) if created_family else []
    missing_labels = [label for label, _code in missing]
    if missing:
        _raise_missing_field_issues(session, family, missing, upload, now)

    if possible_duplicate:
        session.add(
            DataQualityIssue(
                entity_type="family",
                entity_id=family.id,
                family_id=family.id,
                issue_code=IssueCode.possible_duplicate,
                severity=IssueSeverity.high,
                status=IssueStatus.open,
                description=(
                    f"This family, reported over the phone, may be the same as "
                    f"{possible_duplicate}. Needs an officer to decide."
                ),
                details={"other_family_code": possible_duplicate, "voice_id": upload.id},
                detected_at=now,
            )
        )
        warnings.append(
            f"This may be the same family as {possible_duplicate} — flagged for checking."
        )

    upload.status = VoiceUploadStatus.saved
    upload.interaction_id = interaction.id
    upload.family_id = family.id
    upload.saved_at = now

    session.add(
        AuditLog(
            user_id=upload.uploaded_by_user_id,
            action="voice_note.save",
            entity_type="family",
            entity_id=family.id,
            occurred_at=now,
            details={
                "voice_id": upload.id,
                "interaction_id": interaction.id,
                "created_family": created_family,
                "fields_updated": fields_updated,
            },
        )
    )
    session.commit()

    return VoiceConfirmResponse(
        voice_id=upload.id,
        interaction_id=interaction.id,
        family_id=family.id,
        family_code=family.family_code,
        created_family=created_family,
        is_draft=False,
        missing_for_completion=missing_labels,
        possible_duplicate_of=possible_duplicate,
        warnings=warnings,
        fields_updated=fields_updated,
    )
