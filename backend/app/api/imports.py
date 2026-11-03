"""Excel upload and column mapping.

The flow, in order:
  1. POST /api/imports/upload   store the file, read it, guess the columns
  2. PUT  /api/imports/{id}/mapping   he confirms what each column means
  3. (next step) preview, then import

Nothing touches family data in any of this. Reading a sheet changes nothing.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import (
    ActiveColumnOut,
    ColumnOut,
    ColumnsEditIn,
    CommitResponse,
    MappingIn,
    MappingResponse,
    PreviewResponse,
    RowEditIn,
    TargetFieldOut,
    UploadResponse,
)
from app.db import get_session
from app.models import (
    EXTRA_PREFIX,
    CustomField,
    ImportBatch,
    ImportStatus,
    SavedColumnMapping,
)
from app.services.column_mapping import (
    IGNORE,
    TARGET_BY_KEY,
    TARGET_FIELDS,
    apply_llm_suggestions,
    guess_mapping,
    normalise,
    unmapped_required_fields,
)
from app.services.llm import get_llm
from app.services.excel_reader import SheetData, read_sheet
from app.services.import_apply import apply_import
from app.services.import_preview import build_preview
from app.services.storage import get_storage

router = APIRouter(prefix="/api/imports", tags=["imports"])

IST = ZoneInfo("Asia/Kolkata")
ALLOWED_SUFFIXES = (".xlsx", ".xls", ".csv")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _target_out(key: str) -> TargetFieldOut:
    field = TARGET_BY_KEY[key]
    return TargetFieldOut(
        key=field.key, label=field.label, group=field.group, required=field.required
    )


STANDARD_TARGETS = [_target_out(f.key) for f in TARGET_FIELDS]


def all_targets(session: Session) -> list[TargetFieldOut]:
    """Our standard fields plus every extra field already approved.

    Both appear in the same picker, so an extra field added last month is
    offered again rather than created twice under slightly different names.
    """
    extras = session.scalars(
        select(CustomField)
        .where(CustomField.is_active.is_(True))
        .order_by(CustomField.times_used.desc(), CustomField.label)
    ).all()
    return STANDARD_TARGETS + [
        TargetFieldOut(
            key=f"{EXTRA_PREFIX}{field.key}",
            label=field.label,
            group="Extra information",
            required=False,
        )
        for field in extras
    ]


def headers_signature(headers: list[str]) -> str:
    """A fingerprint of the heading row, so the same sheet is recognised again."""
    joined = "|".join(sorted(normalise(h) for h in headers))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _missing_required(mapping_values: set[str | None]) -> list[TargetFieldOut]:
    return [
        _target_out(f.key)
        for f in TARGET_FIELDS
        if f.required and f.key not in mapping_values
    ]


@router.post("/upload", response_model=UploadResponse)
async def upload_sheet(
    file: UploadFile,
    session: Session = Depends(get_session),
) -> UploadResponse:
    filename = file.filename or "upload"
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail="I can only read Excel sheets (.xlsx, .xls) and CSV files.",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 25 MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty.")

    # Store the original file untouched, so we can always go back to it.
    import io

    storage = get_storage()
    storage_key = storage.save(io.BytesIO(contents), filename, folder="imports")

    try:
        sheet = read_sheet(io.BytesIO(contents), filename)
    except Exception as exc:  # noqa: BLE001 - we want the reason shown to him
        storage.delete(storage_key)
        raise HTTPException(
            status_code=400, detail=f"I could not read that sheet: {exc}"
        ) from exc

    if sheet.row_count == 0:
        storage.delete(storage_key)
        raise HTTPException(
            status_code=400,
            detail="I found the column headings but no rows of data underneath them.",
        )

    samples = [sheet.samples(i) for i in range(len(sheet.headers))]
    known_extras = {
        f.key: f.label
        for f in session.scalars(
            select(CustomField).where(CustomField.is_active.is_(True))
        ).all()
    }
    guesses = guess_mapping(sheet.headers, samples, known_extras)

    # Anything the rules could not work out goes to the LLM. Only the
    # headings are sent — never a single row of family data.
    unknown = [g.source_heading for g in guesses if g.target_key is None]
    if unknown:
        llm = get_llm()
        if llm is not None:
            fields = [(f.key, f.label) for f in TARGET_FIELDS]
            extras = list(known_extras.items())
            suggestions = llm.suggest_headings(unknown, fields, extras)
            valid = set(TARGET_BY_KEY) | {
                f"{EXTRA_PREFIX}{key}" for key in known_extras
            }
            apply_llm_suggestions(guesses, suggestions, valid)

    # Have we seen this sheet layout before? If so, use what he said last time.
    signature = headers_signature(sheet.headers)
    saved = session.scalar(
        select(SavedColumnMapping).where(
            SavedColumnMapping.headers_signature == signature
        )
    )
    if saved:
        for guess in guesses:
            remembered = saved.mapping.get(guess.source_heading)
            if remembered:
                guess.target_key = remembered
                guess.confidence = 100
                guess.reason = "You set this last time"

    user = current_user(session)
    batch = ImportBatch(
        original_filename=filename,
        storage_key=storage_key,
        size_bytes=len(contents),
        status=ImportStatus.uploaded,
        sheet_name=sheet.sheet_name,
        header_row_number=sheet.header_row_number,
        row_count=sheet.row_count,
        headers=sheet.headers,
        guessed_mapping=[
            {
                "source_heading": g.source_heading,
                "column_index": g.column_index,
                "target_key": g.target_key,
                "confidence": g.confidence,
                "reason": g.reason,
                "suggested_new_field": g.suggested_new_field,
            }
            for g in guesses
        ],
        uploaded_by_user_id=user.id if user else None,
    )
    session.add(batch)
    session.commit()

    return UploadResponse(
        import_id=batch.id,
        filename=filename,
        sheet_name=sheet.sheet_name,
        header_row_number=sheet.header_row_number,
        row_count=sheet.row_count,
        columns=[
            ColumnOut(
                source_heading=g.source_heading,
                column_index=g.column_index,
                target_key=g.target_key,
                confidence=g.confidence,
                reason=g.reason,
                samples=g.samples,
                suggested_new_field=g.suggested_new_field,
            )
            for g in guesses
        ],
        missing_required=[
            _target_out(f.key) for f in unmapped_required_fields(guesses)
        ],
        target_fields=all_targets(session),
        remembered=saved is not None,
        remembered_label=saved.label if saved else None,
    )


@router.get("/{import_id}", response_model=UploadResponse)
def get_import(
    import_id: int, session: Session = Depends(get_session)
) -> UploadResponse:
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")

    columns = [
        ColumnOut(
            source_heading=g["source_heading"],
            column_index=g["column_index"],
            target_key=batch.confirmed_mapping.get(g["source_heading"], g["target_key"]),
            confidence=g["confidence"],
            reason=g["reason"],
            samples=[],
            suggested_new_field=g.get("suggested_new_field"),
        )
        for g in batch.guessed_mapping
    ]
    return UploadResponse(
        import_id=batch.id,
        filename=batch.original_filename,
        sheet_name=batch.sheet_name,
        header_row_number=batch.header_row_number,
        row_count=batch.row_count,
        columns=columns,
        missing_required=_missing_required({c.target_key for c in columns}),
        target_fields=all_targets(session),
        remembered=False,
    )


@router.put("/{import_id}/mapping", response_model=MappingResponse)
def confirm_mapping(
    import_id: int,
    body: MappingIn,
    session: Session = Depends(get_session),
) -> MappingResponse:
    """He has told us what each column means. Save it, and remember it."""
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")
    if batch.status == ImportStatus.imported:
        raise HTTPException(
            status_code=409, detail="This sheet has already been imported."
        )

    known_headings = set(batch.headers)
    valid_targets = set(TARGET_BY_KEY) | {IGNORE}
    # Extra fields must already have been approved; the screen creates them
    # first, so an unknown one here means something went wrong.
    approved_extras = {
        f.key for f in session.scalars(select(CustomField)).all()
    }

    cleaned: dict[str, str] = {}
    for heading, target in body.mapping.items():
        if heading not in known_headings:
            raise HTTPException(
                status_code=400, detail=f"This sheet has no column called '{heading}'."
            )
        if target.startswith(EXTRA_PREFIX):
            key = target[len(EXTRA_PREFIX) :]
            if key not in approved_extras:
                raise HTTPException(
                    status_code=400,
                    detail=f"The extra field '{key}' has not been added yet.",
                )
        elif target not in valid_targets:
            raise HTTPException(status_code=400, detail=f"Unknown field '{target}'.")
        cleaned[heading] = target

    # Two columns cannot feed the same field.
    used: dict[str, str] = {}
    for heading, target in cleaned.items():
        if target == IGNORE:
            continue
        if target in used:
            name = (
                TARGET_BY_KEY[target].label
                if target in TARGET_BY_KEY
                else target[len(EXTRA_PREFIX) :].replace("_", " ")
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Both '{used[target]}' and '{heading}' are set to "
                    f"'{name}'. Please pick one."
                ),
            )
        used[target] = heading

    batch.confirmed_mapping = cleaned
    missing = _missing_required(set(used))
    batch.status = ImportStatus.uploaded if missing else ImportStatus.mapped

    remembered = False
    if not missing:
        signature = headers_signature(batch.headers)
        saved = session.scalar(
            select(SavedColumnMapping).where(
                SavedColumnMapping.headers_signature == signature
            )
        )
        now = datetime.now(IST)
        if saved:
            saved.mapping = cleaned
            saved.times_used += 1
            saved.last_used_at = now
            if body.remember_as:
                saved.label = body.remember_as
        else:
            session.add(
                SavedColumnMapping(
                    headers_signature=signature,
                    label=body.remember_as or batch.original_filename,
                    headers=batch.headers,
                    mapping=cleaned,
                    last_used_at=now,
                )
            )
        remembered = True

    session.commit()

    return MappingResponse(
        import_id=batch.id,
        status=batch.status.value,
        mapping=cleaned,
        missing_required=missing,
        remembered=remembered,
    )


def _reload_sheet(batch: ImportBatch) -> SheetData:
    """Read the stored file again. The original is never modified."""
    storage = get_storage()
    if not storage.exists(batch.storage_key):
        raise HTTPException(
            status_code=410,
            detail="The uploaded file is no longer on the server. Please upload it again.",
        )
    with storage.open(batch.storage_key) as handle:
        return read_sheet(handle, batch.original_filename)


def _require_mapping(batch: ImportBatch) -> None:
    if not batch.confirmed_mapping:
        raise HTTPException(
            status_code=409,
            detail="Confirm what the columns mean before this step.",
        )


@router.put("/{import_id}/rows/{row_number}", response_model=PreviewResponse)
def edit_row(
    import_id: int,
    row_number: int,
    body: RowEditIn,
    session: Session = Depends(get_session),
) -> PreviewResponse:
    """Correct one row, or leave it out. His Excel file is never changed.

    The whole preview is rebuilt and returned, because one correction can
    change what a row is — fixing a service number can turn a "new family"
    into an update of one we already have.
    """
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")
    if batch.status == ImportStatus.imported:
        raise HTTPException(
            status_code=409, detail="This sheet has already been imported."
        )
    _require_mapping(batch)

    mapped_targets = set(batch.confirmed_mapping.values()) | set(batch.added_fields or {})
    for field_key in body.values:
        if field_key not in mapped_targets:
            raise HTTPException(
                status_code=400,
                detail=f"No column in this sheet is mapped to '{field_key}'.",
            )

    overrides = dict(batch.row_overrides or {})
    entry = {"skip": body.skip, "values": dict(body.values)}
    if not body.skip and not body.values:
        overrides.pop(str(row_number), None)  # back to what the file said
    else:
        overrides[str(row_number)] = entry
    batch.row_overrides = overrides
    session.commit()

    return _build_preview_response(session, batch)


@router.post("/{import_id}/preview", response_model=PreviewResponse)
def preview_import(
    import_id: int, session: Session = Depends(get_session)
) -> PreviewResponse:
    """What would change if this sheet were imported. Writes nothing."""
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")
    if batch.status == ImportStatus.imported:
        raise HTTPException(
            status_code=409, detail="This sheet has already been imported."
        )
    _require_mapping(batch)

    return _build_preview_response(session, batch)


def _label_for(session: Session, field_key: str) -> tuple[str, bool]:
    """(label, required) for a standard field or an approved extra field."""
    if field_key in TARGET_BY_KEY:
        target = TARGET_BY_KEY[field_key]
        return target.label, target.required
    if field_key.startswith(EXTRA_PREFIX):
        key = field_key[len(EXTRA_PREFIX) :]
        custom = session.scalar(select(CustomField).where(CustomField.key == key))
        return (custom.label if custom else key.replace("_", " ")), False
    return field_key, False


def _active_columns(session: Session, batch: ImportBatch, headers: list[str]) -> list[ActiveColumnOut]:
    """Every field this import writes, in sheet order, then the added ones."""
    columns: list[ActiveColumnOut] = []
    mapping = batch.confirmed_mapping or {}
    for heading in headers:
        key = mapping.get(heading)
        if not key or key == IGNORE:
            continue
        label, required = _label_for(session, key)
        columns.append(
            ActiveColumnOut(
                field_key=key, label=label, required=required,
                source_heading=heading, added=False,
            )
        )
    for key, default in (batch.added_fields or {}).items():
        label, required = _label_for(session, key)
        columns.append(
            ActiveColumnOut(
                field_key=key, label=label, required=required,
                source_heading=None, added=True, default_value=default or None,
            )
        )
    return columns


def _build_preview_response(
    session: Session, batch: ImportBatch
) -> PreviewResponse:
    sheet = _reload_sheet(batch)
    preview = build_preview(
        session,
        sheet,
        batch.confirmed_mapping,
        batch.row_overrides or {},
        batch.added_fields or {},
    )

    batch.status = ImportStatus.previewed
    batch.summary = {"counts": preview.counts, "problem_count": preview.problem_count}
    session.commit()

    # to_dict() converts the nested FieldChange objects to plain data too;
    # passing the dataclasses straight through fails validation.
    active = _active_columns(session, batch, sheet.headers)
    in_use = {c.field_key for c in active}
    return PreviewResponse(
        import_id=batch.id,
        filename=batch.original_filename,
        active_columns=active,
        addable_fields=[f for f in all_targets(session) if f.key not in in_use],
        **preview.to_dict(),
    )


@router.put("/{import_id}/columns", response_model=PreviewResponse)
def edit_columns(
    import_id: int,
    body: ColumnsEditIn,
    session: Session = Depends(get_session),
) -> PreviewResponse:
    """Add or remove whole columns from the preview, then show it again.

    Removing a column stops it being imported (his file is not changed).
    Adding a field that is not in his sheet lets him give it a value for
    every row, and fill or fix individual rows with the row editor.
    """
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")
    if batch.status == ImportStatus.imported:
        raise HTTPException(
            status_code=409, detail="This sheet has already been imported."
        )
    _require_mapping(batch)

    mapping = dict(batch.confirmed_mapping or {})
    added = dict(batch.added_fields or {})

    for heading in body.remove_headings:
        if heading not in mapping:
            raise HTTPException(
                status_code=400, detail=f"This sheet has no column called '{heading}'."
            )
        mapping[heading] = IGNORE

    for key in body.remove_added:
        added.pop(key, None)

    approved_extras = {f"{EXTRA_PREFIX}{f.key}" for f in session.scalars(select(CustomField)).all()}
    in_use = {v for v in mapping.values() if v and v != IGNORE}
    for key, default in body.add_fields.items():
        if key not in TARGET_BY_KEY and key not in approved_extras:
            raise HTTPException(status_code=400, detail=f"Unknown field '{key}'.")
        if key in in_use:
            label, _ = _label_for(session, key)
            raise HTTPException(
                status_code=400,
                detail=f"'{label}' already comes from a column in this sheet.",
            )
        added[key] = (default or "").strip()

    # The two names must always have a source, or no family can be made.
    sources = {v for v in mapping.values() if v and v != IGNORE} | set(added)
    missing = [f.label for f in TARGET_FIELDS if f.required and f.key not in sources]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"That would leave no column for: {', '.join(missing)}.",
        )

    batch.confirmed_mapping = mapping
    batch.added_fields = added
    session.commit()

    return _build_preview_response(session, batch)


@router.post("/{import_id}/commit", response_model=CommitResponse)
def commit_import(
    import_id: int, session: Session = Depends(get_session)
) -> CommitResponse:
    """Write the rows. Every change records what it was before."""
    batch = session.get(ImportBatch, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="That upload was not found.")
    if batch.status == ImportStatus.imported:
        raise HTTPException(
            status_code=409, detail="This sheet has already been imported."
        )
    if batch.status != ImportStatus.previewed:
        raise HTTPException(
            status_code=409,
            detail="Look at the preview before importing, so you can see what changes.",
        )
    _require_mapping(batch)

    sheet = _reload_sheet(batch)
    try:
        outcome = apply_import(session, batch, sheet)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        batch = session.get(ImportBatch, import_id)
        if batch is not None:
            batch.status = ImportStatus.failed
            batch.error_message = str(exc)
            session.commit()
        raise HTTPException(
            status_code=500, detail=f"The import failed and nothing was saved: {exc}"
        ) from exc

    batch.status = ImportStatus.imported
    batch.imported_at = datetime.now(IST)
    batch.summary = {**batch.summary, "outcome": outcome.as_dict()}
    session.commit()

    return CommitResponse(
        import_id=batch.id, status=batch.status.value, **outcome.as_dict()
    )
