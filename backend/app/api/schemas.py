"""Shapes of the JSON the API sends and receives."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TargetFieldOut(BaseModel):
    key: str
    label: str
    group: str
    required: bool


class ColumnOut(BaseModel):
    """One column of his sheet, and what we think it means."""

    source_heading: str
    column_index: int
    target_key: str | None
    confidence: int
    reason: str
    samples: list[str]
    # A name proposed for a column that fits none of our fields. Nothing is
    # created until the colonel confirms.
    suggested_new_field: str | None = None


class UploadResponse(BaseModel):
    import_id: int
    filename: str
    sheet_name: str | None
    header_row_number: int | None
    row_count: int
    columns: list[ColumnOut]
    # Required fields nothing points at yet — he must fix these.
    missing_required: list[TargetFieldOut]
    # All the fields he can choose from, for the dropdowns.
    target_fields: list[TargetFieldOut]
    # True when we recognised this sheet layout from a previous upload.
    remembered: bool
    remembered_label: str | None = None


class MappingIn(BaseModel):
    """What he confirmed: his heading -> our field key (or "__ignore__")."""

    mapping: dict[str, str] = Field(default_factory=dict)
    remember_as: str | None = None


class MappingResponse(BaseModel):
    import_id: int
    status: str
    mapping: dict[str, str]
    missing_required: list[TargetFieldOut]
    remembered: bool


# --- preview and import -------------------------------------------------------


class FieldChangeOut(BaseModel):
    field_name: str
    label: str
    old_value: str | None
    new_value: str | None


class RowProblemOut(BaseModel):
    field: str
    code: str
    severity: str
    message: str


class MatchOut(BaseModel):
    family_id: int
    family_code: str
    score: int
    reasons: list[str]


class EditableFieldOut(BaseModel):
    field_key: str
    label: str
    value: str
    edited: bool


class RowEditIn(BaseModel):
    """One row's corrections. Omitted fields are left as the file had them."""

    values: dict[str, str] = Field(default_factory=dict)
    skip: bool = False


class RowPreviewOut(BaseModel):
    row_number: int
    action: str
    fields: list[EditableFieldOut] = Field(default_factory=list)
    edited_fields: list[str] = Field(default_factory=list)
    skipped_by_user: bool = False
    widow_name: str | None
    soldier_name: str | None
    district: str | None
    matched_family_id: int | None
    matched_family_code: str | None
    match_score: int
    match_reasons: list[str]
    other_matches: list[MatchOut]
    changes: list[FieldChangeOut]
    problems: list[RowProblemOut]
    duplicate_of_row: int | None


class ActiveColumnOut(BaseModel):
    """One field this import will write, and where its values come from."""

    field_key: str
    label: str
    required: bool
    # The sheet heading feeding it, or None if he added it on the preview.
    source_heading: str | None
    added: bool
    # For an added field: the value used for every row, if he gave one.
    default_value: str | None = None


class PreviewResponse(BaseModel):
    import_id: int
    filename: str
    total_rows: int
    counts: dict[str, int]
    problem_count: int
    rows: list[RowPreviewOut]
    active_columns: list[ActiveColumnOut] = Field(default_factory=list)
    # Fields he could still add as a column, for the "+ Add a column" picker.
    addable_fields: list[TargetFieldOut] = Field(default_factory=list)


class ColumnsEditIn(BaseModel):
    """Change which fields the import writes, from the preview."""

    # Sheet headings to stop importing.
    remove_headings: list[str] = Field(default_factory=list)
    # Fields with no column in the sheet to add: {field_key: value for every row}.
    add_fields: dict[str, str] = Field(default_factory=dict)
    # Previously added fields to take away again.
    remove_added: list[str] = Field(default_factory=list)


class FamilySearchItem(BaseModel):
    """One line in the family picker."""

    family_id: int
    family_code: str
    primary_contact_name: str
    soldier_name: str | None
    district: str | None
    state: str | None
    is_draft: bool


class VoiceUploadResponse(BaseModel):
    voice_id: int
    filename: str
    language: str
    transcript: str
    summary: str | None
    confidence: int | None
    duration_seconds: int | None
    provider: str
    # Facts heard in the recording, for him to confirm.
    heard: dict[str, Any] = Field(default_factory=dict)
    sentiment: str | None = None
    follow_up_needed: bool = False
    follow_up_note: str | None = None
    # Set when the recording sounds like a family we do not have yet.
    looks_like_new_family: bool = False
    suggested_new_family: dict[str, Any] = Field(default_factory=dict)

    # What the LLM made of the transcript. Always a suggestion — nothing here
    # is saved until he confirms it on the /confirm call.
    suggested_family_id: int | None = None
    suggested_family_code: str | None = None
    suggested_family_confidence: int = 0
    suggested_family_reason: str | None = None
    suggested_field_changes: list[dict[str, str]] = Field(default_factory=list)


class NewFamilyIn(BaseModel):
    """The short form he fills when the voice note is about a new family."""

    widow_name: str | None = None
    soldier_name: str | None = None
    rank: str | None = None
    unit: str | None = None
    service_number: str | None = None
    date_of_death: str | None = None  # DD-MM-YYYY
    cause_of_death: str | None = None
    district: str | None = None
    state: str | None = None
    phone: str | None = None


class VoiceConfirmIn(BaseModel):
    """Either an existing family, or a new draft. Never both."""

    family_id: int | None = None
    new_family: NewFamilyIn | None = None
    # He can correct the transcript before it is saved.
    transcript: str | None = None
    follow_up_needed: bool | None = None
    follow_up_note: str | None = None
    # Field keys from suggested_field_changes that he agreed to apply.
    apply_field_changes: list[str] = Field(default_factory=list)


class VoiceConfirmResponse(BaseModel):
    voice_id: int
    interaction_id: int
    family_id: int
    family_code: str
    created_family: bool
    is_draft: bool
    missing_for_completion: list[str] = Field(default_factory=list)
    possible_duplicate_of: str | None = None
    warnings: list[str] = Field(default_factory=list)
    fields_updated: list[str] = Field(default_factory=list)


class CommitResponse(BaseModel):
    import_id: int
    status: str
    created: int
    updated: int
    unchanged: int
    skipped: int
    duplicates_flagged: int
    needs_decision: int
    excluded: int
    fields_changed: int
    fields_corrected: int
    issues_raised: int
    new_family_codes: list[str]
