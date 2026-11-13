"""The colonel's own field list: his exact headings, his way of writing values.

Rolled back — the development database is left untouched.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db import get_session
from tests.decide import take_the_sheet_via_api
from app.main import app
from app.models import Family
from app.services.column_mapping import guess_mapping
from app.services.import_preview import same_value
from app.services.row_parser import (
    parse_email,
    parse_geolocation,
    parse_sex,
    tidy_name,
)

# Exactly as in his LIST OF FIELDS sheet, spelling mistakes included.
HIS_HEADINGS = [
    "S NO ", "DATE OF CAUALTY", "SERVING UNIT", "SAINIK ARMY NO ", "RANK", "NAME",
    "NAME OF NOK", "RELATIONSHIP", "DISTRICT", "TEHSIL", "TOWN", "VILLAGE",
    "POST OFFICE", "STATE", "PIN CODE", "TELE NO ", "PARENT UNIT ", "GEOLOCATION",
    "Name_of_Child1", "Sex_Child1", "DOB_Child1", "Marital_Status_Child1",
    "Name_of_Child2", "Sex_Child2", "DOB_Child2", "Marital_Status_Child2",
    "Name_of_Child3", "Sex_Child3", "DOB_Child3", "Marital_Status_Child3",
    "Pension Bank", "Pension Bank Branch", "PPO", "Bank_Account _Number",
    "NOK_Telephone", "Email", "CO_Unit_Name", "CO_Unit_Telephone_No1",
    "DOCUMENTS 1", "DOCUMENTS 2", "DOCUMENTS 3", "DOCUMENTS 4",
]


@pytest.fixture
def client(tx_db):
    app.dependency_overrides[get_session] = lambda: tx_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- recognising his headings --------------------------------------------------


def test_every_one_of_his_headings_is_recognised_without_the_llm():
    guesses = guess_mapping(HIS_HEADINGS, [[] for _ in HIS_HEADINGS])
    unmatched = [g.source_heading for g in guesses if g.target_key is None]
    assert unmatched == []


def test_his_headings_go_to_the_right_fields():
    mapped = {
        g.source_heading.strip(): g.target_key
        for g in guess_mapping(HIS_HEADINGS, [[] for _ in HIS_HEADINGS])
    }
    assert mapped["DATE OF CAUALTY"] == "date_of_death"  # his spelling
    assert mapped["NAME"] == "soldier_name"
    assert mapped["NAME OF NOK"] == "widow_name"
    assert mapped["SAINIK ARMY NO"] == "service_number"
    assert mapped["PARENT UNIT"] == "regiment"
    assert mapped["SERVING UNIT"] == "unit"
    assert mapped["TOWN"] == "town"
    assert mapped["VILLAGE"] == "village_or_town"
    assert mapped["PPO"] == "ppo_number"
    assert mapped["Pension Bank Branch"] == "bank_branch"
    assert mapped["NOK_Telephone"] == "alternate_phone"
    assert mapped["Name_of_Child2"] == "child2_name"
    assert mapped["DOB_Child3"] == "child3_dob"


def test_document_columns_are_not_read_as_data():
    guesses = guess_mapping(["DOCUMENTS 1", "DOCUMENTS 4"], [[], []])
    assert all(g.target_key == "__ignore__" for g in guesses)


def test_the_word_name_alone_does_not_swallow_other_headings():
    """'NAME' means the soldier, but 'Ward Member Name' must not."""
    guesses = guess_mapping(["NAME", "Ward Member Name"], [[], []])
    assert guesses[0].target_key == "soldier_name"
    assert guesses[1].target_key != "soldier_name"


# --- his way of writing values ---------------------------------------------------


def test_titles_are_removed_from_names():
    assert tidy_name("SMT VEDVATE") == "Vedvate"
    assert tidy_name("SMT HARDIP KAUR") == "Hardip Kaur"
    assert tidy_name("Late Rajvir Singh") == "Rajvir Singh"
    assert tidy_name("Shri. Dara Singh") == "Dara Singh"
    # A name that is only a title is left alone rather than emptied.
    assert tidy_name("SMT") == "Smt"


def test_kumari_is_kept_because_it_is_also_a_first_name():
    assert tidy_name("Kumari Devi") == "Kumari Devi"


def test_gps_is_read_in_either_shape():
    assert parse_geolocation("28.6139, 77.2090")[0] == "28.613900, 77.209000"
    assert parse_geolocation("28.6139 77.2090")[0] == "28.613900, 77.209000"
    assert parse_geolocation("not a place")[0] is None
    assert parse_geolocation("128.6, 77.2")[0] is None  # latitude out of range


def test_sex_is_read_from_m_and_f():
    assert parse_sex("M")[0] == "male"
    assert parse_sex("f")[0] == "female"
    assert parse_sex("X")[0] is None


def test_email_is_checked():
    assert parse_email("Sunita@Mail.com")[0] == "sunita@mail.com"
    assert parse_email("not an email")[0] is None


def test_capitals_alone_are_not_a_change():
    assert same_value("Wife", "WIFE")
    assert same_value("Palakkad  Main", "palakkad main")
    assert not same_value("Palakkad", "Moga")
    assert not same_value(None, "Moga")


# --- importing a row in his format ------------------------------------------------


def his_workbook(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HIS_HEADINGS)
    for row in rows:
        sheet.append(row + [""] * (len(HIS_HEADINGS) - len(row)))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def his_row() -> list:
    values = {
        "S NO ": 1, "DATE OF CAUALTY": "01-04-2021", "SERVING UNIT": "19 RAJPUT",
        "SAINIK ARMY NO ": "77001122", "RANK": "SEP", "NAME": "ZZZ DARA TESTSINGH",
        "NAME OF NOK": "SMT ZZZ ASHA TESTSINGH", "RELATIONSHIP": "WIFE",
        "DISTRICT": "Kanpur Urban", "TEHSIL": "GHATAMPUR", "TOWN": "GHATAMPUR",
        "VILLAGE": "SYONDI", "POST OFFICE": "GHATAMPUR", "STATE": "Uttar Pradesh",
        "PIN CODE": "209206", "TELE NO ": "9876511223", "PARENT UNIT ": "The Rajput Regiment",
        "GEOLOCATION": "26.1520, 80.1680", "Pension Bank": "State Bank of India",
        "Pension Bank Branch": "Ghatampur Branch", "PPO": "S/123456/2021",
        "Bank_Account _Number": "12345678901", "NOK_Telephone": "9876511224",
        "Email": "asha@mockmail.example", "CO_Unit_Name": "19 Rajput",
        "CO_Unit_Telephone_No1": "9876511225",
    }
    return [values.get(h, "") for h in HIS_HEADINGS]


def import_rows(client, rows):
    up = client.post(
        "/api/imports/upload", files={"file": ("his.xlsx", his_workbook(rows))}
    ).json()
    mapping = {c["source_heading"]: c["target_key"] or "__ignore__" for c in up["columns"]}
    client.put(f"/api/imports/{up['import_id']}/mapping", json={"mapping": mapping})
    preview = client.post(f"/api/imports/{up['import_id']}/preview").json()
    # He takes the sheet's value for every change (each needs his choice).
    take_the_sheet_via_api(client, up["import_id"])
    result = client.post(f"/api/imports/{up['import_id']}/commit").json()
    return preview, result


def test_a_row_in_his_format_saves_every_field(client, tx_db):
    _, result = import_rows(client, [his_row()])
    assert result["created"] == 1

    family = tx_db.scalars(
        select(Family).where(Family.ppo_number == "S/123456/2021")
    ).first()
    assert family is not None
    assert family.primary_contact_name == "Zzz Asha Testsingh"  # title removed
    assert family.nok_relationship == "WIFE"
    assert family.tehsil == "GHATAMPUR"
    assert family.town == "GHATAMPUR"
    assert family.village_or_town == "SYONDI"
    assert family.post_office == "GHATAMPUR"
    assert family.bank_branch == "Ghatampur Branch"
    assert family.email == "asha@mockmail.example"
    assert family.co_unit_phone == "+919876511225"
    assert family.gps_coordinates == "26.152000, 80.168000"
    assert family.location is not None  # placed on the map
    assert family.soldier.regiment == "The Rajput Regiment"
    assert family.soldier.unit == "19 RAJPUT"


# --- children ---------------------------------------------------------------------

from app.models import FamilyMember, FieldHistory  # noqa: E402
from app.models.enums import Relation  # noqa: E402


def with_children(row: list, children: list[tuple]) -> list:
    """children: (name, sex, dob, marital) for slots 1, 2, 3."""
    row = list(row)
    for slot, (name, sex, dob, marital) in enumerate(children, start=1):
        row[HIS_HEADINGS.index(f"Name_of_Child{slot}")] = name
        row[HIS_HEADINGS.index(f"Sex_Child{slot}")] = sex
        row[HIS_HEADINGS.index(f"DOB_Child{slot}")] = dob
        row[HIS_HEADINGS.index(f"Marital_Status_Child{slot}")] = marital
    return row


THREE = [
    ("ZZZ RAHUL TESTSINGH", "M", "05-06-2010", "Unmarried"),
    ("ZZZ PRIYA TESTSINGH", "F", "12-01-2004", "Married"),
    ("ZZZ AMAN TESTSINGH", "M", "20-09-2015", "Unmarried"),
]


def children_of(tx_db, ppo="S/123456/2021") -> list[FamilyMember]:
    tx_db.expire_all()
    family = tx_db.scalars(select(Family).where(Family.ppo_number == ppo)).first()
    return sorted(
        (m for m in family.members if m.relation != Relation.widow),
        key=lambda m: m.full_name,
    )


def test_three_child_columns_become_three_child_records(client, tx_db):
    import_rows(client, [with_children(his_row(), THREE)])
    kids = children_of(tx_db)
    assert [k.full_name for k in kids] == [
        "Zzz Aman Testsingh", "Zzz Priya Testsingh", "Zzz Rahul Testsingh",
    ]
    priya = kids[1]
    assert priya.relation == Relation.daughter
    assert priya.gender == "female"
    assert priya.date_of_birth.isoformat() == "2004-01-12"
    assert priya.marital_status == "Married"
    assert priya.is_married is True
    assert kids[2].relation == Relation.son


def test_empty_child_slots_add_nothing(client, tx_db):
    import_rows(client, [with_children(his_row(), THREE[:1])])
    assert len(children_of(tx_db)) == 1


def test_importing_the_same_sheet_again_does_not_duplicate_children(client, tx_db):
    row = with_children(his_row(), THREE)
    import_rows(client, [row])
    preview, result = import_rows(client, [row])
    assert preview["rows"][0]["action"] == "unchanged"
    assert len(children_of(tx_db)) == 3


def test_a_changed_child_detail_is_an_update_with_history(client, tx_db):
    import_rows(client, [with_children(his_row(), THREE)])
    changed = list(THREE)
    changed[0] = ("ZZZ RAHUL TESTSINGH", "M", "06-06-2010", "Unmarried")  # DOB fixed
    preview, _ = import_rows(client, [with_children(his_row(), changed)])

    row = preview["rows"][0]
    # One digit different in a date: flagged as a possible typo for him to check.
    assert row["action"] == "possible_typo"
    change = next(c for c in row["changes"] if c["field_name"] == "child.1.date_of_birth")
    assert change["old_value"] == "05-06-2010"
    assert change["new_value"] == "06-06-2010"
    assert change["typo"] == "One digit different"

    rahul = next(k for k in children_of(tx_db) if k.full_name.startswith("Zzz Rahul"))
    assert rahul.date_of_birth.isoformat() == "2010-06-06"
    history = tx_db.scalars(
        select(FieldHistory).where(
            FieldHistory.entity_type == "family_member",
            FieldHistory.entity_id == rahul.id,
            FieldHistory.field_name == "date_of_birth",
        )
    ).first()
    assert history.old_value == "2010-06-05"


def test_a_new_child_in_a_later_sheet_is_added(client, tx_db):
    import_rows(client, [with_children(his_row(), THREE[:2])])
    preview, _ = import_rows(client, [with_children(his_row(), THREE)])
    added = [c for c in preview["rows"][0]["changes"] if c["field_name"] == "child.3"]
    assert added and "new child" in added[0]["new_value"]
    assert len(children_of(tx_db)) == 3


def test_a_child_left_out_of_a_later_sheet_is_not_deleted(client, tx_db):
    """A blank means 'no information', never 'remove'."""
    import_rows(client, [with_children(his_row(), THREE)])
    import_rows(client, [with_children(his_row(), THREE[:1])])
    assert len(children_of(tx_db)) == 3


def test_a_child_is_matched_by_date_of_birth_if_the_name_is_spelled_differently(
    client, tx_db
):
    import_rows(client, [with_children(his_row(), THREE[:1])])
    respelled = [("ZZZ RAAHUL TESTSINGH", "M", "05-06-2010", "Unmarried")]
    preview, _ = import_rows(client, [with_children(his_row(), respelled)])
    kids = children_of(tx_db)
    assert len(kids) == 1, "a spelling change created a second child"
    assert kids[0].full_name == "Zzz Raahul Testsingh"


def test_cea_fields_start_empty(client, tx_db):
    """Agreed: the CEA-only fields exist but are left blank for now."""
    import_rows(client, [his_row()])
    family = tx_db.scalars(
        select(Family).where(Family.ppo_number == "S/123456/2021")
    ).first()
    assert family.record_office is None
    assert family.correspondence_address is None
    assert family.bank_account_holder is None
