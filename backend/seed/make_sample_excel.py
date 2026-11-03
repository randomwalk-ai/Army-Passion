"""Create sample Excel sheets in the colonel's own format.

The column headings are exactly those in the `LIST OF FIELDS` sheet of his
`LIST OF FIELDS.xlsx`, spellings included ("DATE OF CAUALTY",
"Bank_Account _Number"). Values are written the way his sample data writes
them: capitals, "SMT" before the NOK's name, short ranks (HAV, SEP, NK),
M/F for sex.

EVERYTHING IS FAKE.

Run:  python -m seed.make_sample_excel
Makes:
  sample_data/widows_sheet_sample.xlsx               his format
  sample_data/widows_sheet_with_extra_columns.xlsx   his format + 3 unknown columns
"""

from __future__ import annotations

import random

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import PROJECT_ROOT
from app.db import SessionLocal
from app.models import Family, Soldier
from app.models.enums import Relation
from seed import reference_data as ref

rng = random.Random(4242)

OUT_DIR = PROJECT_ROOT / "sample_data"

# Exactly as in his LIST OF FIELDS sheet.
HEADERS = [
    "S NO", "DATE OF CAUALTY", "SERVING UNIT", "SAINIK ARMY NO", "RANK", "NAME",
    "NAME OF NOK", "RELATIONSHIP", "DISTRICT", "TEHSIL", "TOWN", "VILLAGE",
    "POST OFFICE", "STATE", "PIN CODE", "TELE NO", "PARENT UNIT", "GEOLOCATION",
    "Name_of_Child1", "Sex_Child1", "DOB_Child1", "Marital_Status_Child1",
    "Name_of_Child2", "Sex_Child2", "DOB_Child2", "Marital_Status_Child2",
    "Name_of_Child3", "Sex_Child3", "DOB_Child3", "Marital_Status_Child3",
    "Pension Bank", "Pension Bank Branch", "PPO", "Bank_Account _Number",
    "NOK_Telephone", "Email", "CO_Unit_Name", "CO_Unit_Telephone_No1",
    "DOCUMENTS 1", "DOCUMENTS 2", "DOCUMENTS 3", "DOCUMENTS 4",
]
COLUMN = {name: i for i, name in enumerate(HEADERS)}

# His sheet uses short ranks.
SHORT_RANK = {
    "Sepoy": "SEP", "Lance Naik": "L NK", "Naik": "NK", "Havildar": "HAV",
    "Naib Subedar": "NB SUB", "Subedar": "SUB", "Subedar Major": "SUB MAJ",
    "Rifleman": "RFN", "Gunner": "GNR", "Lieutenant": "LT", "Captain": "CAPT",
    "Major": "MAJ",
}

TEHSILS = ["SADAR", "KHARKHODA", "MEHAM", "BARWALA", "NANGAL", "PHAGWARA", "GOHANA"]
TOWNS = ["RAMPURA", "SOHNA", "KALANAUR", "LADWA", "SAFIDON", "TOSHAM", "HANSI"]
VILLAGES = ["KARONTHA", "SYONDI", "KANSALA", "NAMOL", "RISALI", "TONGOU", "KHERA"]


def blank_row() -> list:
    return [""] * len(HEADERS)


def set_cell(row: list, heading: str, value) -> None:
    row[COLUMN[heading]] = "" if value is None else value


def date_text(value) -> str:
    """Mostly DD-MM-YYYY, sometimes DD/MM/YYYY, as typed sheets mix them."""
    if value is None:
        return ""
    if rng.random() < 0.8:
        return value.strftime("%d-%m-%Y")
    return value.strftime("%d/%m/%Y")


def fake_digits(n: int) -> str:
    return str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randint(0, 9)) for _ in range(n - 1))


def documents_for(army_no: str) -> list[str]:
    """File names in his convention: ArmyNo.Owner.Type.Year.PgNo.Extn"""
    if rng.random() < 0.5:
        return ["", "", "", ""]
    return [
        f"{army_no}.NOK.ServiceBooklet.2024.1.pdf",
        f"{army_no}.Child1.Marksheet.2025.1.pdf" if rng.random() < 0.5 else "",
        "",
        "",
    ]


def rows_for_existing_families(limit: int = 12) -> list[list]:
    """Families already in the database, some with a changed detail.

    These make the preview show real updates, the case that matters most.
    """
    session = SessionLocal()
    try:
        families = session.scalars(
            select(Family)
            .join(Soldier, Soldier.id == Family.soldier_id)
            .where(
                Family.primary_phone.is_not(None),
                Soldier.service_number.is_not(None),
                Soldier.date_of_death.is_not(None),
            )
            .options(selectinload(Family.members), selectinload(Family.soldier))
            .limit(limit)
        ).all()

        rows = []
        for index, family in enumerate(families):
            soldier = family.soldier
            changed = index % 4 != 3  # leave every fourth one identical
            row = blank_row()
            set_cell(row, "DATE OF CAUALTY", soldier.date_of_death.strftime("%d-%m-%Y"))
            set_cell(row, "SERVING UNIT", soldier.unit)
            set_cell(row, "SAINIK ARMY NO", soldier.service_number)
            set_cell(row, "RANK", soldier.rank)
            set_cell(row, "NAME", soldier.full_name.upper())
            set_cell(row, "NAME OF NOK", f"SMT {family.primary_contact_name.upper()}")
            set_cell(row, "RELATIONSHIP", (family.nok_relationship or "Wife").upper())
            set_cell(row, "DISTRICT", family.district)
            set_cell(row, "TEHSIL", family.tehsil)
            set_cell(row, "TOWN", family.town)
            set_cell(row, "VILLAGE", family.village_or_town)
            set_cell(row, "POST OFFICE", family.post_office)
            set_cell(row, "STATE", family.state)
            set_cell(row, "PIN CODE", family.pincode)
            phone = fake_digits(10) if changed else (family.primary_phone or "").replace("+91", "")
            set_cell(row, "TELE NO", phone)
            set_cell(row, "PARENT UNIT", soldier.regiment)
            set_cell(row, "GEOLOCATION", family.gps_coordinates)

            children = [
                m for m in family.members if m.relation in (Relation.son, Relation.daughter)
            ][:3]
            for slot, child in enumerate(children, start=1):
                set_cell(row, f"Name_of_Child{slot}", child.full_name.upper())
                set_cell(row, f"Sex_Child{slot}", "M" if child.gender == "male" else "F")
                set_cell(row, f"DOB_Child{slot}", date_text(child.date_of_birth))
                set_cell(row, f"Marital_Status_Child{slot}", child.marital_status or "Unmarried")

            set_cell(row, "Pension Bank", family.bank_name)
            branch = family.bank_branch
            if changed and branch:
                branch = branch.replace("Main", "Cantt") if "Main" in branch else f"{family.district} Main Branch"
            set_cell(row, "Pension Bank Branch", branch)
            set_cell(row, "PPO", family.ppo_number)
            set_cell(row, "Bank_Account _Number", family.bank_account_number)
            set_cell(row, "NOK_Telephone", (family.alternate_phone or "").replace("+91", ""))
            set_cell(row, "Email", family.email)
            set_cell(row, "CO_Unit_Name", family.co_unit_name)
            set_cell(row, "CO_Unit_Telephone_No1", (family.co_unit_phone or "").replace("+91", ""))
            for i, name in enumerate(documents_for(soldier.service_number), start=1):
                set_cell(row, f"DOCUMENTS {i}", name)
            rows.append(row)
        return rows
    finally:
        session.close()


def build_new_row() -> list:
    """Someone not in the database, written the way his sheet writes it."""
    district, state, lat, lon, language = rng.choice(ref.DISTRICTS)

    soldier_first = rng.choice(ref.MALE_FIRST_NAMES[language])
    widow_first = rng.choice(ref.FEMALE_FIRST_NAMES[language])
    if language.value == "punjabi":
        soldier_surname, widow_surname = "Singh", "Kaur"
    else:
        soldier_surname = rng.choice(ref.SURNAMES[language])
        widow_surname = soldier_surname

    rank = rng.choices(
        [r for r, _ in ref.RANKS_WEIGHTED], weights=[w for _, w in ref.RANKS_WEIGHTED]
    )[0]
    regiment = rng.choice(ref.REGIMENT_BY_STATE.get(state, ref.REGIMENTS))
    army_no = f"{rng.randint(1000000, 19999999)}{rng.choice(['', '', 'A', 'H', 'K'])}"

    from datetime import date, timedelta

    death = date.today() - timedelta(days=rng.randint(60, 12 * 365))

    row = blank_row()
    set_cell(row, "DATE OF CAUALTY", date_text(death))
    # "Rajput Regiment" -> "7 RAJPUT", the short form his sheet uses.
    short = [w for w in regiment.split() if w.lower() not in {"the", "regiment", "corps", "of"}]
    set_cell(
        row, "SERVING UNIT",
        f"{rng.randint(1, 22)} {(short[0] if short else regiment).upper()}",
    )
    set_cell(row, "SAINIK ARMY NO", army_no)
    set_cell(row, "RANK", SHORT_RANK.get(rank, rank.upper()))
    set_cell(row, "NAME", f"{soldier_first} {soldier_surname}".upper())
    set_cell(row, "NAME OF NOK", f"SMT {widow_first} {widow_surname}".upper())
    set_cell(row, "RELATIONSHIP", "WIFE")
    set_cell(row, "DISTRICT", district)
    set_cell(row, "TEHSIL", rng.choice(TEHSILS))
    set_cell(row, "TOWN", rng.choice(TOWNS))
    village = rng.choice(VILLAGES)
    set_cell(row, "VILLAGE", village)
    set_cell(row, "POST OFFICE", village if rng.random() < 0.5 else district.upper())
    set_cell(row, "STATE", state)
    set_cell(row, "PIN CODE", rng.choice(["", str(rng.randint(110001, 799999))]))
    set_cell(row, "TELE NO", rng.choices([fake_digits(10), ""], weights=[88, 12])[0])
    set_cell(row, "PARENT UNIT", regiment)
    if rng.random() < 0.7:
        set_cell(
            row, "GEOLOCATION",
            f"{lat + rng.uniform(-0.2, 0.2):.6f}, {lon + rng.uniform(-0.2, 0.2):.6f}",
        )

    for slot in range(1, rng.randint(0, 3) + 1):
        is_boy = rng.random() < 0.5
        name = rng.choice(ref.BOY_CHILD_NAMES if is_boy else ref.GIRL_CHILD_NAMES)
        surname = ("Singh" if is_boy else "Kaur") if language.value == "punjabi" else widow_surname
        age = rng.randint(2, 26)
        set_cell(row, f"Name_of_Child{slot}", f"{name} {surname}".upper())
        set_cell(row, f"Sex_Child{slot}", "M" if is_boy else "F")
        set_cell(
            row, f"DOB_Child{slot}",
            date_text(date.today() - timedelta(days=age * 365 + rng.randint(0, 364))),
        )
        set_cell(
            row, f"Marital_Status_Child{slot}",
            "Married" if age >= 22 and rng.random() < 0.4 else "Unmarried",
        )

    set_cell(row, "Pension Bank", rng.choice(ref.BANKS))
    set_cell(row, "Pension Bank Branch", f"{district} {rng.choice(['Main', 'Cantt', 'City'])} Branch")
    set_cell(row, "PPO", f"{rng.choice(['S', 'F'])}/{rng.randint(100000, 999999)}/{death.year}")
    set_cell(row, "Bank_Account _Number", rng.choice(["", str(rng.randint(10**10, 10**11 - 1))]))
    set_cell(row, "NOK_Telephone", fake_digits(10) if rng.random() < 0.4 else "")
    if rng.random() < 0.3:
        set_cell(row, "Email", f"{widow_first.lower()}{rng.randint(10, 99)}@mockmail.example")
    set_cell(row, "CO_Unit_Name", f"{rng.randint(1, 22)} {regiment}")
    set_cell(row, "CO_Unit_Telephone_No1", fake_digits(10) if rng.random() < 0.6 else "")
    for i, name in enumerate(documents_for(army_no), start=1):
        set_cell(row, f"DOCUMENTS {i}", name)
    return row


def write_sheet(path, headers: list[str], rows: list[list]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "LIST OF FIELDS"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for index, heading in enumerate(headers, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(
            12, len(heading) + 3
        )
    workbook.save(path)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    try:
        existing = rows_for_existing_families()
    except Exception as exc:  # noqa: BLE001 - still useful without them
        print(f"  (could not read existing families: {exc})")
        existing = []

    rows = existing + [build_new_row() for _ in range(48)]

    # A few duplicates, the way a re-typed sheet gets them.
    for source in rng.sample(range(len(rows)), 3):
        rows.append(list(rows[source]))

    for number, row in enumerate(rows, start=1):
        row[COLUMN["S NO"]] = number

    path = OUT_DIR / "widows_sheet_sample.xlsx"
    write_sheet(path, HEADERS, rows)
    print(f"Wrote {path}")
    print(f"  {len(rows)} rows, {len(HEADERS)} columns (his exact headings)")
    print(f"  {len(existing)} rows are families already in the database")
    print(f"  {len(rows) - len(existing) - 3} rows are new, plus 3 duplicates")

    extra_headers = HEADERS + ["Ward Member Name", "Panchayat", "Zone Code"]
    members = ["SURESH KUMAR", "RAMESH LAL", "HARBANS SINGH", "MEENA DEVI", ""]
    panchayats = ["KOTLA", "NANGAL", "RAMPUR", "KHERA", "DHANI"]
    extra_rows = [
        list(row) + [members[i % 5], panchayats[i % 5], f"Z-{i % 7 + 1}"]
        for i, row in enumerate(rows[:30])
    ]
    extra_path = OUT_DIR / "widows_sheet_with_extra_columns.xlsx"
    write_sheet(extra_path, extra_headers, extra_rows)
    print(f"\nWrote {extra_path}")
    print("  Same format, plus 3 columns we have no field for:")
    print("  Ward Member Name, Panchayat, Zone Code")


if __name__ == "__main__":
    main()
