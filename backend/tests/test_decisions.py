"""His choices on the preview: likely typos, updates and possible duplicates.

Nothing about a family we already have changes without his say. Each value
that would change needs "Keep database", "Take Excel" or a value he types,
and Import is refused until every one is decided. Everything rolls back.
"""

import pytest
from sqlalchemy import select

from app.models import Family, Soldier
from app.services.import_apply import UndecidedRows, apply_import
from app.services.import_preview import RowAction, build_preview
from app.services.matching import words_close
from app.services.typos import typo_reason
from tests.test_import import MAPPING, make_batch, sheet_of


def a_family(session) -> Family:
    family = session.scalars(
        select(Family)
        .join(Soldier, Soldier.id == Family.soldier_id)
        .where(
            Family.is_draft.is_(False),
            Family.primary_phone.is_not(None),
            Soldier.service_number.is_not(None),
            Soldier.date_of_death.is_not(None),
        )
        .limit(1)
    ).first()
    if family is None:
        pytest.skip("No suitable seeded family — run seed.generate --reset")
    return family


def its_row(family: Family, phone: str | None = None, district: str | None = None) -> list[str]:
    soldier = family.soldier
    return [
        family.primary_contact_name, soldier.full_name, soldier.service_number,
        phone or family.primary_phone[-10:], soldier.date_of_death.strftime("%d-%m-%Y"),
        district or family.district or "", family.state or "", "",
    ]


def one_digit_off(phone: str) -> str:
    digits = phone[-10:]
    return digits[:-1] + ("1" if digits[-1] != "1" else "2")


def decide(batch, row_number: int, **entry) -> None:
    overrides = dict(batch.row_overrides or {})
    overrides[str(row_number)] = {"skip": False, "values": {}, **entry}
    batch.row_overrides = overrides


# --- telling a typo from a real change ----------------------------------------


@pytest.mark.parametrize(
    "field, old, new, reason",
    [
        ("primary_phone", "+919876543210", "+919876543211", "Only 1 digit different"),
        ("primary_phone", "+919876543210", "+918123456789", None),
        ("soldier.date_of_death", "05-03-2021", "03-05-2021", "Day and month swapped"),
        ("soldier.date_of_death", "05-03-2021", "17-11-2019", None),
        ("soldier.service_number", "4373680Y", "4373681Y", "One character different"),
        ("primary_contact_name", "Sunita Devi", "Suneeta Devi", "Spelt slightly differently"),
        ("primary_contact_name", "Sunita Devi", "Kamla Rani", None),
        ("annual_income", "90000", "90001", None),
        ("child.1.gender", "male", "female", None),
    ],
)
def test_typos_are_told_apart_from_real_changes(field, old, new, reason):
    assert typo_reason(field, old, new) == reason


@pytest.mark.parametrize(
    "a, b, close",
    [("sunita", "suneeta", True), ("gurpreet", "gurprit", True), ("kaur", "kour", True),
     ("sunita", "sita", False), ("anita", "amita", False), ("ram", "raj", False)],
)
def test_names_spelt_differently_are_recognised(a, b, close):
    assert words_close(a, b) is close


# --- the preview --------------------------------------------------------------


def test_a_one_digit_phone_change_is_a_possible_typo_waiting_for_him(tx_db):
    family = a_family(tx_db)
    sheet = sheet_of([its_row(family, phone=one_digit_off(family.primary_phone))])
    row = build_preview(tx_db, sheet, MAPPING).rows[0]
    assert row.action == RowAction.possible_typo
    change = next(c for c in row.changes if c.field_name == "primary_phone")
    assert change.typo == "Only 1 digit different"
    assert change.decision is None and row.undecided == 1


def test_a_real_change_is_an_update_that_still_needs_his_choice(tx_db):
    family = a_family(tx_db)
    sheet = sheet_of([its_row(family, district="Zzzdecidepur")])
    row = build_preview(tx_db, sheet, MAPPING).rows[0]
    assert row.action == RowAction.update
    assert row.undecided == 1


def test_import_is_refused_until_everything_is_decided(tx_db):
    family = a_family(tx_db)
    sheet = sheet_of([its_row(family, district="Zzzdecidepur")])
    with pytest.raises(UndecidedRows):
        apply_import(tx_db, make_batch(tx_db), sheet)


# --- what each choice saves ---------------------------------------------------


def test_keep_database_leaves_the_value_alone(tx_db):
    family = a_family(tx_db)
    old_phone = family.primary_phone
    sheet = sheet_of([its_row(family, phone=one_digit_off(old_phone))])
    batch = make_batch(tx_db)
    decide(batch, 2, decisions={"primary_phone": "keep"})
    apply_import(tx_db, batch, sheet)
    tx_db.flush()
    assert family.primary_phone == old_phone


def test_take_excel_saves_the_sheets_value(tx_db):
    family = a_family(tx_db)
    new_phone = one_digit_off(family.primary_phone)
    sheet = sheet_of([its_row(family, phone=new_phone)])
    batch = make_batch(tx_db)
    decide(batch, 2, decisions={"primary_phone": "excel"})
    apply_import(tx_db, batch, sheet)
    tx_db.flush()
    assert family.primary_phone == f"+91{new_phone}"


def test_a_value_he_types_counts_as_decided_and_is_saved(tx_db):
    family = a_family(tx_db)
    sheet = sheet_of([its_row(family, phone=one_digit_off(family.primary_phone))])
    batch = make_batch(tx_db)
    decide(batch, 2, values={"phone": "9812312312"})
    row = build_preview(tx_db, sheet, MAPPING, batch.row_overrides).rows[0]
    assert row.undecided == 0
    assert next(c for c in row.changes if c.field_name == "primary_phone").decision == "typed"
    apply_import(tx_db, batch, sheet)
    tx_db.flush()
    assert family.primary_phone == "+919812312312"


# --- through the API, as the screen does it -----------------------------------


@pytest.fixture
def client(tx_db):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_api_refuses_import_then_accepts_after_the_choice(client, tx_db):
    from tests.test_api_imports import upload

    family = a_family(tx_db)
    soldier = family.soldier
    row = [1, family.primary_contact_name, soldier.full_name, soldier.service_number,
           one_digit_off(family.primary_phone), soldier.date_of_death.strftime("%d-%m-%Y"),
           family.district or "", family.state or "", ""]
    body = upload(client, [row]).json()
    mapping = {c["source_heading"]: c["target_key"] or "__ignore__" for c in body["columns"]}
    client.put(f"/api/imports/{body['import_id']}/mapping", json={"mapping": mapping})
    preview = client.post(f"/api/imports/{body['import_id']}/preview").json()
    assert preview["undecided"] == {"possible_typo": 1}

    refused = client.post(f"/api/imports/{body['import_id']}/commit")
    assert refused.status_code == 409
    assert "Decide 1 row first" in refused.json()["detail"]

    number = preview["rows"][0]["row_number"]
    decided = client.put(
        f"/api/imports/{body['import_id']}/rows/{number}/decision",
        json={"decisions": {"primary_phone": "keep"}},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["undecided"] == {}
    assert client.post(f"/api/imports/{body['import_id']}/commit").status_code == 200


# --- the same family twice in one sheet ----------------------------------------

NEW_A = ["Zzz Sunita Pairtest", "Zzz Ram Pairtest", "", "9000033333", "05-03-2021",
         "Zzzpairpur", "Haryana", ""]
# The same family, typed again with the widow's name spelt differently and a new phone.
NEW_A_AGAIN = ["Zzz Suneeta Pairtest", "Zzz Ram Pairtest", "", "9000044444", "05-03-2021",
               "Zzzpairpur", "Haryana", ""]


def test_an_exact_copy_in_the_sheet_is_skipped_by_itself(tx_db):
    rows = build_preview(tx_db, sheet_of([NEW_A, list(NEW_A)]), MAPPING).rows
    assert rows[1].action == RowAction.duplicate_in_file
    assert rows[1].undecided == 0
    assert "exact copy of row 2" in rows[1].note


def test_a_lookalike_row_in_the_sheet_waits_for_him(tx_db):
    rows = build_preview(tx_db, sheet_of([NEW_A, NEW_A_AGAIN]), MAPPING).rows
    assert rows[0].action == RowAction.create
    second = rows[1]
    assert second.action == RowAction.lookalike_in_file
    assert second.pair_with_row == 2 and second.undecided == 1
    marks = {c["label"]: c["mark"] for c in second.pair_comparison}
    assert marks["Name of NOK"] == "~" and marks["Phone"] == "!=" and marks["Soldier"] == "="
    with pytest.raises(UndecidedRows):
        apply_import(tx_db, make_batch(tx_db), sheet_of([NEW_A, NEW_A_AGAIN]))


@pytest.mark.parametrize(
    "pair, created, kept_name",
    [("first", 1, "Zzz Sunita Pairtest"), ("second", 1, "Zzz Suneeta Pairtest"), ("both", 2, None)],
)
def test_his_choice_for_lookalike_rows_decides_what_is_added(tx_db, pair, created, kept_name):
    sheet = sheet_of([NEW_A, NEW_A_AGAIN])
    batch = make_batch(tx_db)
    decide(batch, 3, pair=pair)
    outcome = apply_import(tx_db, batch, sheet)
    tx_db.flush()
    assert outcome.created == created
    names = set(
        tx_db.scalars(
            select(Family.primary_contact_name).where(Family.district == "Zzzpairpur")
        ).all()
    )
    assert len(names) == created
    if kept_name:
        assert names == {kept_name}
