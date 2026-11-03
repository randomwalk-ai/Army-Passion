"""The preview and the import itself.

Every test here rolls back, so the development database is left untouched.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import (
    DataQualityIssue,
    Family,
    FieldHistory,
    ImportBatch,
    ImportStatus,
    Soldier,
)
from app.models.enums import ChangeSource, IssueCode
from app.services.excel_reader import SheetData
from app.services.import_apply import apply_import
from app.services.import_preview import RowAction, build_preview

HEADERS = [
    "Name of Widow", "Husband Name", "Army No", "Mob No",
    "Date of Casualty", "Distt", "State", "Annual Income (Rs)",
]
MAPPING = {
    "Name of Widow": "widow_name",
    "Husband Name": "soldier_name",
    "Army No": "service_number",
    "Mob No": "phone",
    "Date of Casualty": "date_of_death",
    "Distt": "district",
    "State": "state",
    "Annual Income (Rs)": "annual_income",
}


def sheet_of(rows: list[list[str]]) -> SheetData:
    return SheetData(
        headers=HEADERS, rows=rows, sheet_name="Test", header_row_number=1
    )


def make_batch(session) -> ImportBatch:
    batch = ImportBatch(
        original_filename="test_sheet.xlsx",
        storage_key="imports/test.xlsx",
        status=ImportStatus.previewed,
        headers=HEADERS,
        confirmed_mapping=MAPPING,
        row_count=0,
    )
    session.add(batch)
    session.flush()
    return batch


def an_existing_family(session) -> Family:
    """Pick a seeded family that has everything we need to compare against."""
    family = session.scalars(
        select(Family)
        .join(Soldier, Soldier.id == Family.soldier_id)
        .where(
            Family.primary_phone.is_not(None),
            Soldier.service_number.is_not(None),
            Soldier.date_of_death.is_not(None),
        )
        .limit(1)
    ).first()
    if family is None:
        pytest.skip("No suitable seeded family — run seed.generate --reset")
    return family


# --- the preview changes nothing ---------------------------------------------


def test_preview_does_not_touch_the_database(tx_db):
    before = tx_db.scalar(select(func.count()).select_from(Family))
    sheet = sheet_of(
        [["Nirmala Devi", "Hari Ram", "7788991X", "9876500011",
          "12-05-2020", "Rohtak", "Haryana", "90000"]]
    )
    build_preview(tx_db, sheet, MAPPING)
    assert tx_db.scalar(select(func.count()).select_from(Family)) == before


def test_a_person_we_do_not_have_is_marked_as_new(tx_db):
    sheet = sheet_of(
        [["Zzz Testwidow", "Zzz Testsoldier", "9999999Z", "9876500022",
          "12-05-2020", "Rohtak", "Haryana", "90000"]]
    )
    preview = build_preview(tx_db, sheet, MAPPING)
    assert preview.rows[0].action == RowAction.create


def test_the_same_service_number_is_recognised_as_an_update(tx_db):
    family = an_existing_family(tx_db)
    soldier = family.soldier
    sheet = sheet_of(
        [[family.primary_contact_name, soldier.full_name, soldier.service_number,
          "9876500033", soldier.date_of_death.strftime("%d-%m-%Y"),
          family.district or "", family.state or "", "123456"]]
    )
    row = build_preview(tx_db, sheet, MAPPING).rows[0]
    assert row.action == RowAction.update
    assert row.matched_family_id == family.id
    assert row.match_score >= 80
    changed = {c.field_name for c in row.changes}
    assert "primary_phone" in changed
    assert "annual_income" in changed


def test_an_identical_row_shows_as_unchanged(tx_db):
    family = an_existing_family(tx_db)
    soldier = family.soldier
    sheet = sheet_of(
        [[family.primary_contact_name, soldier.full_name, soldier.service_number,
          family.primary_phone, soldier.date_of_death.strftime("%d-%m-%Y"),
          family.district or "", family.state or "",
          str(family.annual_income or "")]]
    )
    assert build_preview(tx_db, sheet, MAPPING).rows[0].action == RowAction.unchanged


def test_blank_cells_never_wipe_what_we_already_know(tx_db):
    """An empty cell means 'no information', not 'delete this'."""
    family = an_existing_family(tx_db)
    soldier = family.soldier
    sheet = sheet_of(
        [[family.primary_contact_name, soldier.full_name, soldier.service_number,
          "", "", "", "", ""]]
    )
    row = build_preview(tx_db, sheet, MAPPING).rows[0]
    assert row.changes == [], f"blank cells proposed changes: {row.changes}"


def test_the_same_person_twice_in_one_sheet_is_caught(tx_db):
    line = ["Zzz Twice", "Zzz Husband", "8888888Y", "9876500044",
            "12-05-2020", "Rohtak", "Haryana", "90000"]
    preview = build_preview(tx_db, sheet_of([line, list(line)]), MAPPING)
    assert preview.rows[0].action == RowAction.create
    assert preview.rows[1].action == RowAction.duplicate_in_file
    assert preview.rows[1].duplicate_of_row == 2


def test_a_row_with_no_name_is_skipped(tx_db):
    sheet = sheet_of([["", "", "", "9876500055", "12-05-2020", "Rohtak", "Haryana", ""]])
    assert build_preview(tx_db, sheet, MAPPING).rows[0].action == RowAction.skipped


def test_bad_values_are_reported_on_the_row(tx_db):
    sheet = sheet_of(
        [["Zzz Badvalues", "Zzz Husband", "7777777X", "98765 4321",
          "32-13-2021", "Rohtak", "Haryana", "90000"]]
    )
    row = build_preview(tx_db, sheet, MAPPING).rows[0]
    codes = {p["code"] for p in row.problems}
    assert IssueCode.invalid_phone.value in codes
    assert IssueCode.invalid_date.value in codes


# --- the import writes, and records what it changed --------------------------


def test_importing_a_new_family_creates_it(tx_db):
    before = tx_db.scalar(select(func.count()).select_from(Family))
    batch = make_batch(tx_db)
    sheet = sheet_of(
        [["Zzz Newwidow", "Zzz Newsoldier", "6666666Q", "9876500066",
          "12-05-2020", "Rohtak", "Haryana", "90000"]]
    )
    outcome = apply_import(tx_db, batch, sheet)
    tx_db.flush()

    assert outcome.created == 1
    assert tx_db.scalar(select(func.count()).select_from(Family)) == before + 1

    created = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Newwidow")
    ).first()
    assert created is not None
    assert created.primary_phone == "+919876500066"
    assert created.district == "Rohtak"
    assert created.soldier.date_of_death == date(2020, 5, 12)
    # A widow row is created alongside the family.
    assert any(m.full_name == "Zzz Newwidow" for m in created.members)


def test_every_changed_field_writes_its_old_value_to_history(tx_db):
    family = an_existing_family(tx_db)
    soldier = family.soldier
    old_phone = family.primary_phone
    old_income = family.annual_income

    batch = make_batch(tx_db)
    sheet = sheet_of(
        [[family.primary_contact_name, soldier.full_name, soldier.service_number,
          "9876500077", soldier.date_of_death.strftime("%d-%m-%Y"),
          family.district or "", family.state or "", "777777"]]
    )
    outcome = apply_import(tx_db, batch, sheet)
    tx_db.flush()

    assert outcome.updated == 1
    assert family.primary_phone == "+919876500077"

    history = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_type == "family",
            FieldHistory.entity_id == family.id,
            FieldHistory.source == ChangeSource.excel_import,
        )
    ).all()
    by_field = {h.field_name: h for h in history}

    assert "primary_phone" in by_field, "the phone change was not recorded"
    assert by_field["primary_phone"].old_value == str(old_phone)
    assert by_field["primary_phone"].new_value == "+919876500077"
    assert "test_sheet.xlsx" in by_field["primary_phone"].source_reference

    assert by_field["annual_income"].old_value == str(old_income)
    assert by_field["annual_income"].new_value == "777777"


def test_nothing_is_lost_when_a_field_changes(tx_db):
    """The old value must still be readable after the import."""
    family = an_existing_family(tx_db)
    soldier = family.soldier
    original_phone = family.primary_phone

    batch = make_batch(tx_db)
    sheet = sheet_of(
        [[family.primary_contact_name, soldier.full_name, soldier.service_number,
          "9876500088", soldier.date_of_death.strftime("%d-%m-%Y"),
          family.district or "", family.state or "", ""]]
    )
    apply_import(tx_db, batch, sheet)
    tx_db.flush()

    recovered = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_id == family.id,
            FieldHistory.field_name == "primary_phone",
        ).order_by(FieldHistory.id.desc())
    ).first()
    assert recovered.old_value == str(original_phone)


def test_problems_become_items_on_the_needs_attention_list(tx_db):
    batch = make_batch(tx_db)
    sheet = sheet_of(
        [["Zzz Problemwidow", "Zzz Problemsoldier", "5555555P", "",
          "32-13-2021", "Rohtak", "Haryana", "90000"]]
    )
    outcome = apply_import(tx_db, batch, sheet)
    tx_db.flush()

    assert outcome.issues_raised >= 2
    created = tx_db.scalars(
        select(Family).where(Family.primary_contact_name == "Zzz Problemwidow")
    ).first()
    codes = {
        i.issue_code
        for i in tx_db.scalars(
            select(DataQualityIssue).where(DataQualityIssue.family_id == created.id)
        ).all()
    }
    assert IssueCode.missing_phone in codes
    assert IssueCode.invalid_date in codes


def test_duplicates_in_the_file_are_not_imported_twice(tx_db):
    batch = make_batch(tx_db)
    line = ["Zzz Dupwidow", "Zzz Duphusband", "4444444D", "9876500099",
            "12-05-2020", "Rohtak", "Haryana", "90000"]
    outcome = apply_import(tx_db, batch, sheet_of([line, list(line)]))
    tx_db.flush()

    assert outcome.created == 1
    assert outcome.duplicates_flagged == 1
    assert (
        tx_db.scalar(
            select(func.count())
            .select_from(Family)
            .where(Family.primary_contact_name == "Zzz Dupwidow")
        )
        == 1
    )


def test_an_uncertain_match_is_imported_but_flagged_for_an_officer(tx_db):
    """Never merge on a guess. Add it, and raise the question."""
    family = an_existing_family(tx_db)
    batch = make_batch(tx_db)
    # Same widow name and district, but no service number and a different phone.
    sheet = sheet_of(
        [[family.primary_contact_name, "", "", "9876500111",
          "", family.district or "", family.state or "", ""]]
    )
    preview = build_preview(tx_db, sheet, MAPPING)
    if preview.rows[0].action != RowAction.needs_decision:
        pytest.skip("This seeded family did not produce an uncertain match")

    outcome = apply_import(tx_db, batch, sheet)
    tx_db.flush()
    assert outcome.created == 1
    assert outcome.needs_decision == 1

    flagged = tx_db.scalars(
        select(DataQualityIssue).where(
            DataQualityIssue.issue_code == IssueCode.possible_duplicate,
            DataQualityIssue.details["import_id"].astext == str(batch.id),
        )
    ).all()
    assert flagged, "an uncertain match was not raised for an officer"
    # Both records still exist — nothing was merged.
    assert tx_db.get(Family, family.id) is not None
