"""Build the mock database.

Run with:   python -m seed.generate --reset

Everything is FAKE. The generator is seeded with a fixed number, so running it
twice produces exactly the same data — that makes bugs reproducible.
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Application,
    ApplicationStageEvent,
    AuditLog,
    DataQualityIssue,
    Document,
    Family,
    FamilyMember,
    FamilySchemeEligibility,
    FieldHistory,
    Interaction,
    Philanthropist,
    PhilanthropistMatch,
    Posting,
    Scheme,
    Soldier,
    User,
)
from app.models.enums import (
    ApplicationStage,
    ChangeSource,
    DeathCauseCategory,
    DocumentStatus,
    DocumentType,
    DutyStatus,
    IssueCode,
    IssueSeverity,
    IssueStatus,
    Language,
    PhilanthropistInterest,
    Relation,
    UserRole,
)
from seed import reference_data as ref
from seed.mock_schemes import MOCK_SCHEMES
from seed.mock_transcripts import TRANSCRIPTS

SEED = 20261022
IST = ZoneInfo("Asia/Kolkata")
TODAY = date.today()
NOW = datetime.now(IST)

TOTAL_FAMILIES = 150
DUPLICATE_PAIRS = 3  # near-duplicate records deliberately planted

rng = random.Random(SEED)


# --- small helpers ------------------------------------------------------------


def weighted_choice(pairs: list[tuple]):
    values = [p[0] for p in pairs]
    weights = [p[1] for p in pairs]
    return rng.choices(values, weights=weights, k=1)[0]


def fake_phone() -> str:
    return "+91" + str(rng.choice([6, 7, 8, 9])) + "".join(
        str(rng.randint(0, 9)) for _ in range(9)
    )


def fake_service_number(rank: str) -> str:
    if rank in {"Lieutenant", "Captain", "Major"}:
        return f"IC-{rng.randint(50000, 89999)}"
    return f"{rng.randint(1000000, 9999999)}{rng.choice('ABCFHKLMNPWY')}"


def point(lat: float, lon: float) -> str:
    """EWKT string — GeoAlchemy2 understands this directly."""
    return f"SRID=4326;POINT({lon:.6f} {lat:.6f})"


def jitter(lat: float, lon: float) -> tuple[float, float]:
    """Scatter a family around the district centre so the map isn't one dot."""
    return lat + rng.uniform(-0.25, 0.25), lon + rng.uniform(-0.25, 0.25)


def years_ago(years: int, spread_days: int = 300) -> date:
    return TODAY - timedelta(days=years * 365 + rng.randint(0, spread_days))


# High-altitude stations where snow and extreme cold are plausible all winter.
HIGH_ALTITUDE = {
    "Siachen Base Camp", "Leh", "Kargil", "Drass", "Tawang", "Gangtok",
    "Pithoragarh",
}


HIGH_ALTITUDE_STATIONS = [s for s in ref.POSTING_STATIONS if s[0] in HIGH_ALTITUDE]


def pick_death_place(sub_cause: str) -> tuple[str, str]:
    """Some causes can only happen in the mountains. Keep place and cause honest."""
    if sub_cause in {
        "Avalanche",
        "Frostbite complications",
        "High altitude pulmonary oedema",
    }:
        return rng.choice(HIGH_ALTITUDE_STATIONS)
    return rng.choice(ref.POSTING_STATIONS)


def plausible_weather(sub_cause: str, place: str, when: date) -> str:
    """Weather that fits the cause, the place and the season.

    The colonel wants to warn units about real patterns, so a random weather
    value would make the insights worthless.
    """
    month = when.month
    winter = month in (11, 12, 1, 2)
    monsoon = month in (6, 7, 8, 9)
    summer = month in (4, 5, 6)
    high = place in HIGH_ALTITUDE

    # Some causes imply their own conditions.
    if sub_cause in {"Avalanche", "Frostbite complications"}:
        return rng.choice(["Heavy snowfall", "Extreme cold"])
    if sub_cause == "High altitude pulmonary oedema":
        return rng.choice(["Extreme cold", "Clear"])
    if sub_cause == "Heat stroke on duty":
        return "Heat wave"
    if sub_cause in {"Landslide", "Drowning", "Drowning during exercise"}:
        return rng.choice(["Rain", "Thunderstorm"]) if monsoon else rng.choice(["Rain", "Cloudy"])

    if high and winter:
        return rng.choice(["Heavy snowfall", "Extreme cold", "Clear"])
    if high:
        return rng.choice(["Clear", "Extreme cold", "Cloudy"])
    if winter:
        return rng.choice(["Dense fog", "Clear", "Cloudy", "Extreme cold"])
    if monsoon:
        return rng.choice(["Rain", "Thunderstorm", "Cloudy"])
    if summer:
        return rng.choice(["Heat wave", "Clear", "Clear"])
    return rng.choice(["Clear", "Cloudy"])


TEHSILS = ["Sadar", "Kharkhoda", "Meham", "Barwala", "Nangal", "Phagwara",
           "Gohana", "Jhajjar", "Narnaul", "Rajgarh", "Kotkapura", "Mansa"]
TOWNS = ["Rampura", "Sohna", "Kalanaur", "Bhiwani Khera", "Ladwa", "Safidon",
         "Tosham", "Dharuhera", "Bahadurgarh", "Hansi", "Ratia", "Pehowa"]


def fill_colonel_fields(family, soldier, district: str, lat: float, lon: float, index: int):
    """Fill the fields from the colonel's own field list.

    Uses its own random generator, seeded per family, so adding these fields
    does not change any of the mock data that already existed.

    Fields the CEA form needs but his list does not have (record office,
    school details...) are deliberately left EMPTY, as agreed.
    """
    extra = random.Random(f"{SEED}-colonel-{index}")
    family.nok_relationship = "Wife"
    family.town = extra.choice(TOWNS)
    family.tehsil = extra.choice(TEHSILS)
    family.post_office = f"{family.town} PO"
    family.gps_coordinates = f"{lat:.6f}, {lon:.6f}"
    year = soldier.date_of_death.year if soldier.date_of_death else TODAY.year
    family.ppo_number = f"{extra.choice(['S', 'F'])}/{extra.randint(100000, 999999)}/{year}"
    family.bank_branch = f"{district} {extra.choice(['Main', 'Cantt', 'City', 'Bazaar'])} Branch"
    if extra.random() < 0.4:
        first = family.primary_contact_name.split()[0].lower()
        family.email = f"{first}.{extra.randint(10, 99)}@mockmail.example"
    family.co_unit_name = soldier.unit
    family.co_unit_phone = "+91" + str(extra.choice([6, 7, 8, 9])) + "".join(
        str(extra.randint(0, 9)) for _ in range(9)
    )


def pick_name(language: Language, female: bool) -> tuple[str, str]:
    pool = ref.FEMALE_FIRST_NAMES if female else ref.MALE_FIRST_NAMES
    first = rng.choice(pool[language])
    if language == Language.punjabi:
        surname = "Kaur" if female else "Singh"
        return first, surname
    return first, rng.choice(ref.SURNAMES[language])


# --- wipe ---------------------------------------------------------------------


def reset(session: Session) -> None:
    """Delete every row, children first. Only ever used on the mock database."""
    for model in (
        PhilanthropistMatch,
        Philanthropist,
        ApplicationStageEvent,
        Application,
        FamilySchemeEligibility,
        Document,
        Interaction,
        DataQualityIssue,
        FieldHistory,
        AuditLog,
        FamilyMember,
        Family,
        Posting,
        Soldier,
        Scheme,
        User,
    ):
        session.execute(delete(model))
    session.commit()


# --- builders -----------------------------------------------------------------


def create_users(session: Session) -> dict[str, User]:
    """The colonel, two officers, an admin and two volunteers."""
    colonel = User(
        full_name="Vikram Singh Rathore",
        rank="Colonel (Retd)",
        email="colonel@armypassion.mock",
        phone=fake_phone(),
        role=UserRole.colonel,
    )
    admin = User(
        full_name="Anjali Deshpande",
        rank=None,
        email="admin@armypassion.mock",
        phone=fake_phone(),
        role=UserRole.admin,
    )
    officers = [
        User(
            full_name="Major Harinder Pal Sidhu (Retd)",
            rank="Major (Retd)",
            email="officer1@armypassion.mock",
            phone=fake_phone(),
            role=UserRole.officer,
        ),
        User(
            full_name="Subedar Major Ramanathan K (Retd)",
            rank="Subedar Major (Retd)",
            email="officer2@armypassion.mock",
            phone=fake_phone(),
            role=UserRole.officer,
        ),
    ]
    volunteers = [
        User(
            full_name="Priya Nair",
            email="volunteer1@armypassion.mock",
            phone=fake_phone(),
            role=UserRole.volunteer,
        ),
        User(
            full_name="Gurpreet Singh Bedi",
            email="volunteer2@armypassion.mock",
            phone=fake_phone(),
            role=UserRole.volunteer,
        ),
    ]

    session.add_all([colonel, admin, *officers, *volunteers])
    session.flush()

    # The colonel's own career. These are what talking points are matched against.
    colonel_career = [
        ("Jammu & Kashmir Rifles", "Udhampur", "Jammu & Kashmir", 1989, 1992),
        ("Jammu & Kashmir Rifles", "Srinagar", "Jammu & Kashmir", 1992, 1995),
        ("Rajputana Rifles", "Bikaner", "Rajasthan", 1995, 1998),
        ("Rajputana Rifles", "Drass", "Ladakh", 1998, 2001),
        ("16 Infantry Division", "Jalandhar Cantt", "Punjab", 2001, 2005),
        ("Army HQ", "Delhi Cantt", "Delhi", 2005, 2009),
        ("8 Mountain Division", "Baramulla", "Jammu & Kashmir", 2009, 2013),
        ("15 Corps", "Leh", "Ladakh", 2013, 2017),
        ("Western Command", "Ambala Cantt", "Haryana", 2017, 2020),
    ]
    for unit, place, state, frm, to in colonel_career:
        session.add(
            Posting(
                user_id=colonel.id,
                unit=unit,
                formation=rng.choice(ref.FORMATIONS),
                place=place,
                state=state,
                from_year=frm,
                to_year=to,
            )
        )

    session.flush()
    return {
        "colonel": colonel,
        "admin": admin,
        "officers": officers,
        "volunteers": volunteers,
        "colonel_career": colonel_career,
    }


def create_schemes(session: Session) -> list[Scheme]:
    schemes = [
        Scheme(
            code=s["code"],
            name=s["name"],
            authority=s["authority"],
            category=s["category"],
            description=s["description"],
            benefit_amount=s["benefit_amount"],
            benefit_description=s["benefit_description"],
            is_recurring=s["is_recurring"],
            rules=s["rules"],
            required_documents=s["required_documents"],
            is_mock=True,
            is_active=True,
            source_reference="INVENTED FOR DEVELOPMENT - replace with official KSB/state rules",
        )
        for s in MOCK_SCHEMES
    ]
    session.add_all(schemes)
    session.flush()
    return schemes


def build_soldier_and_family(
    session: Session,
    index: int,
    colonel_career: list[tuple],
    force_fog_accident: bool = False,
) -> tuple[Soldier, Family]:
    district, state, lat, lon, language = rng.choice(ref.DISTRICTS)
    if force_fog_accident:
        # Pick from the fog belt so the winter pattern shows up on the map.
        candidates = [d for d in ref.DISTRICTS if d[0] in ref.FOG_BELT_DISTRICTS]
        district, state, lat, lon, language = rng.choice(candidates)

    # --- the soldier ---
    s_first, s_surname = pick_name(language, female=False)
    rank = weighted_choice(ref.RANKS_WEIGHTED)
    regiment = rng.choice(ref.REGIMENT_BY_STATE.get(state, ref.REGIMENTS))

    age_at_death = rng.randint(24, 52)
    years_dead = rng.randint(0, 12)
    date_of_death = years_ago(years_dead)
    date_of_birth = date_of_death - timedelta(days=age_at_death * 365 + rng.randint(0, 364))
    date_of_enrolment = date_of_birth + timedelta(days=rng.randint(18, 23) * 365)

    if force_fog_accident:
        cause = DeathCauseCategory.accident
        sub_cause = "Two-wheeler road accident"
        weather = "Dense fog"
        duty = DutyStatus.on_leave
        # Force a December/January date — the foggy months.
        year = date_of_death.year
        month = rng.choice([12, 1])
        day = rng.randint(1, 28)
        date_of_death = date(year if month == 12 else year + 1, month, day)
        if date_of_death > TODAY:
            date_of_death = date(year - 1, month, day)
        death_place = f"{district} - {rng.choice(['NH-7', 'NH-44', 'State Highway 11', 'village road'])}"
        death_district, death_state = district, state
        d_lat, d_lon = jitter(lat, lon)
    else:
        cause = weighted_choice(ref.CAUSE_WEIGHTS)
        sub_cause = rng.choice(ref.CAUSES[cause])
        duty = rng.choices(
            [DutyStatus.on_duty, DutyStatus.on_leave, DutyStatus.unknown],
            weights=[62, 30, 8],
        )[0]
        death_place, death_state = pick_death_place(sub_cause)
        death_district = death_place
        weather = plausible_weather(sub_cause, death_place, date_of_death)
        d_lat, d_lon = jitter(lat, lon)

    soldier = Soldier(
        full_name=f"{s_first} {s_surname}",
        rank=rank,
        service_number=fake_service_number(rank),
        regiment=regiment,
        unit=f"{rng.randint(1, 22)} {regiment}",
        date_of_birth=date_of_birth,
        date_of_enrolment=date_of_enrolment,
        date_of_death=date_of_death,
        cause_category=cause,
        cause_sub_category=sub_cause,
        place_of_death=death_place,
        district_of_death=death_district,
        state_of_death=death_state,
        weather_at_death=weather,
        duty_status=duty,
        death_location=point(d_lat, d_lon),
    )
    session.add(soldier)
    session.flush()

    # --- postings: 2 to 5, and for roughly a third of soldiers one of them
    # deliberately overlaps the colonel's career so talking points exist ---
    n_postings = rng.randint(2, 5)
    service_start = date_of_enrolment.year
    service_end = date_of_death.year
    overlap_with_colonel = rng.random() < 0.35

    span = max(1, (service_end - service_start) // n_postings)
    year_cursor = service_start
    for i in range(n_postings):
        frm = year_cursor
        to = min(service_end, frm + span)
        if to <= frm:
            to = frm + 1
        place, p_state = rng.choice(ref.POSTING_STATIONS)

        if overlap_with_colonel and i == rng.randint(0, n_postings - 1):
            # Reuse one of the colonel's own postings, with overlapping years.
            c_unit, c_place, c_state, c_frm, c_to = rng.choice(colonel_career)
            if c_to >= service_start and c_frm <= service_end:
                place, p_state = c_place, c_state
                frm = max(service_start, c_frm)
                to = min(service_end, c_to)
                if to <= frm:
                    to = frm + 1

        session.add(
            Posting(
                soldier_id=soldier.id,
                unit=f"{rng.randint(1, 22)} {regiment}",
                formation=rng.choice(ref.FORMATIONS),
                place=place,
                state=p_state,
                from_year=frm,
                to_year=to,
            )
        )
        year_cursor = to
        if year_cursor >= service_end:
            break

    # --- the family ---
    w_first, w_surname = pick_name(language, female=True)
    if language == Language.punjabi:
        w_surname = "Kaur"
    else:
        w_surname = s_surname  # widow usually shares the soldier's surname

    f_lat, f_lon = jitter(lat, lon)
    income = rng.choice([60000, 90000, 120000, 150000, 200000, 260000, 340000, 480000])

    family = Family(
        family_code=f"AP-{TODAY.year}-{index + 1:04d}",
        soldier_id=soldier.id,
        primary_contact_name=f"{w_first} {w_surname}",
        primary_phone=fake_phone(),
        alternate_phone=fake_phone() if rng.random() < 0.35 else None,
        whatsapp_opted_in=rng.random() < 0.55,
        preferred_language=language,
        address_line=f"House No. {rng.randint(1, 450)}, {rng.choice(['Ward', 'Gali', 'Mohalla', 'Street'])} {rng.randint(1, 20)}",
        village_or_town=rng.choice(
            ["Rampur", "Nangal", "Kotla", "Bhagwanpur", "Chak", "Sultanpur",
             "Khera", "Dhani", "Pind", "Palayam", "Wadi", "Para"]
        )
        + f" ({district})",
        district=district,
        state=state,
        pincode=str(rng.randint(110001, 799999)),
        location=point(f_lat, f_lon),
        bank_account_number=str(rng.randint(10**10, 10**11 - 1)),
        bank_ifsc=f"{rng.choice(['SBIN', 'PUNB', 'CNRB', 'BARB', 'UBIN', 'IDIB'])}0{rng.randint(100000, 999999)}",
        bank_name=rng.choice(ref.BANKS),
        monthly_pension_amount=rng.choice([0, 9000, 12000, 15000, 18000, 22000]),
        annual_income=income,
        last_verified_on=TODAY - timedelta(days=rng.randint(20, 700)),
        last_contacted_on=TODAY - timedelta(days=rng.randint(3, 400)),
    )
    fill_colonel_fields(family, soldier, district, f_lat, f_lon, index)
    session.add(family)
    session.flush()

    # --- family members ---
    widow_age = rng.randint(26, 78)
    session.add(
        FamilyMember(
            family_id=family.id,
            full_name=f"{w_first} {w_surname}",
            relation=Relation.widow,
            date_of_birth=TODAY - timedelta(days=widow_age * 365 + rng.randint(0, 364)),
            gender="female",
            is_married=False,  # widowed
            is_employed=rng.random() < 0.25,
            has_disability=rng.random() < 0.06,
            education_level=rng.choice(["Class 5", "Class 8", "Class 10", "Class 12", "Graduate"]),
            aadhaar_last4=f"{rng.randint(0, 9999):04d}",
        )
    )

    for _ in range(rng.randint(0, 3)):
        is_boy = rng.random() < 0.52
        child_age = rng.randint(1, 27)
        dob = TODAY - timedelta(days=child_age * 365 + rng.randint(0, 364))
        session.add(
            FamilyMember(
                family_id=family.id,
                full_name=f"{rng.choice(ref.BOY_CHILD_NAMES if is_boy else ref.GIRL_CHILD_NAMES)} {w_surname if language != Language.punjabi else ('Singh' if is_boy else 'Kaur')}",
                relation=Relation.son if is_boy else Relation.daughter,
                date_of_birth=dob,
                gender="male" if is_boy else "female",
                is_studying=child_age <= 24 and rng.random() < 0.75,
                education_level=rng.choice(ref.EDUCATION_LEVELS),
                is_married=child_age >= 21 and rng.random() < 0.35,
                is_employed=child_age >= 19 and rng.random() < 0.3,
                has_disability=rng.random() < 0.05,
                aadhaar_last4=f"{rng.randint(0, 9999):04d}",
            )
        )
    session.flush()
    for member in family.members:
        if member.relation in (Relation.son, Relation.daughter):
            member.marital_status = "Married" if member.is_married else "Unmarried"

    # An elderly dependent parent in some families.
    if rng.random() < 0.22:
        p_first, _ = pick_name(language, female=rng.random() < 0.6)
        session.add(
            FamilyMember(
                family_id=family.id,
                full_name=f"{p_first} {s_surname}",
                relation=rng.choice([Relation.father, Relation.mother]),
                date_of_birth=TODAY - timedelta(days=rng.randint(68, 88) * 365),
                gender=rng.choice(["male", "female"]),
                has_disability=rng.random() < 0.15,
            )
        )

    session.flush()
    return soldier, family


def add_children_turning_18(session: Session, families: list[Family]) -> int:
    """Plant children who cross 18 in the next three months.

    This is what the "becomes eligible later" alert has to catch.
    """
    chosen = rng.sample(families, 12)
    for family in chosen:
        is_boy = rng.random() < 0.5
        days_to_birthday = rng.randint(5, 88)
        dob = TODAY - timedelta(days=18 * 365 + 4) + timedelta(days=days_to_birthday)
        surname = family.primary_contact_name.split()[-1]
        session.add(
            FamilyMember(
                family_id=family.id,
                full_name=f"{rng.choice(ref.BOY_CHILD_NAMES if is_boy else ref.GIRL_CHILD_NAMES)} {surname}",
                relation=Relation.son if is_boy else Relation.daughter,
                date_of_birth=dob,
                gender="male" if is_boy else "female",
                is_studying=True,
                education_level="Class 12",
                is_married=False,
                has_disability=False,
                aadhaar_last4=f"{rng.randint(0, 9999):04d}",
            )
        )
    session.flush()
    return len(chosen)


def create_documents(session: Session, families: list[Family], officers: list[User]) -> int:
    count = 0
    for family in families:
        wanted = rng.sample(
            [
                DocumentType.death_certificate,
                DocumentType.aadhaar,
                DocumentType.bank_passbook,
                DocumentType.discharge_book,
                DocumentType.pension_payment_order,
                DocumentType.marriage_certificate,
            ],
            k=rng.randint(3, 6),
        )
        for doc_type in wanted:
            status = rng.choices(
                [
                    DocumentStatus.officer_approved,
                    DocumentStatus.ai_extracted,
                    DocumentStatus.uploaded,
                    DocumentStatus.missing,
                    DocumentStatus.rejected,
                ],
                weights=[48, 18, 14, 16, 4],
            )[0]

            approved_at = None
            approver = None
            storage_key = None
            extracted: dict = {}
            confidence = None
            mismatches: list = []

            if status != DocumentStatus.missing:
                storage_key = f"mock/families/{family.id}/{doc_type.value}.pdf"
                extracted = {
                    "name_on_document": family.primary_contact_name,
                    "document_number": f"MOCK{rng.randint(10**7, 10**8 - 1)}",
                }
                confidence = rng.randint(62, 99)
                if confidence < 80 and rng.random() < 0.5:
                    mismatches = [
                        {
                            "field": "name_on_document",
                            "database_value": family.primary_contact_name,
                            "document_value": family.primary_contact_name.replace("a", "aa", 1),
                            "note": "Spelling differs - officer should confirm",
                        }
                    ]
            if status == DocumentStatus.officer_approved:
                approver = rng.choice(officers)
                approved_at = NOW - timedelta(days=rng.randint(1, 500))

            session.add(
                Document(
                    family_id=family.id,
                    doc_type=doc_type,
                    status=status,
                    storage_key=storage_key,
                    original_filename=f"{doc_type.value}.pdf" if storage_key else None,
                    mime_type="application/pdf" if storage_key else None,
                    size_bytes=rng.randint(80_000, 3_000_000) if storage_key else None,
                    extracted_fields=extracted,
                    extraction_confidence=confidence,
                    mismatches=mismatches,
                    approved_by_user_id=approver.id if approver else None,
                    approved_at=approved_at,
                    rejection_reason=(
                        "Scan unreadable, asked family to resend"
                        if status == DocumentStatus.rejected
                        else None
                    ),
                )
            )
            count += 1
    session.flush()
    return count


def create_applications(
    session: Session, families: list[Family], schemes: list[Scheme], users: dict
) -> tuple[int, int]:
    """Applications spread across the pipeline, with some deliberately stuck."""
    officers = users["officers"]
    total = 0
    stuck = 0
    ref_counter = 1

    for family in families:
        for scheme in rng.sample(schemes, k=rng.randint(0, 3)):
            stage = rng.choices(
                [
                    ApplicationStage.form_filled,
                    ApplicationStage.verified_signed,
                    ApplicationStage.submitted,
                    ApplicationStage.received,
                    ApplicationStage.money_credited,
                    ApplicationStage.rejected,
                ],
                weights=[16, 14, 22, 12, 30, 6],
            )[0]

            make_stuck = (
                stage
                not in {ApplicationStage.money_credited, ApplicationStage.rejected}
                and rng.random() < 0.22
            )
            days_in_stage = rng.randint(45, 240) if make_stuck else rng.randint(1, 25)
            stage_changed_on = TODAY - timedelta(days=days_in_stage)

            credited_on = None
            amount_credited = None
            if stage == ApplicationStage.money_credited:
                credited_on = stage_changed_on
                amount_credited = scheme.benefit_amount

            app = Application(
                reference_code=f"AP-APP-{ref_counter:05d}",
                family_id=family.id,
                scheme_id=scheme.id,
                stage=stage,
                stage_changed_on=stage_changed_on,
                stuck_after_days=30,
                ksb_dak_id=(
                    f"KSB/DAK/{rng.randint(2022, TODAY.year)}/{rng.randint(10000, 99999)}"
                    if stage
                    in {
                        ApplicationStage.submitted,
                        ApplicationStage.received,
                        ApplicationStage.money_credited,
                    }
                    else None
                ),
                amount_claimed=scheme.benefit_amount,
                amount_credited=amount_credited,
                credited_on=credited_on,
                assigned_to_user_id=rng.choice(officers).id,
                rejection_reason=(
                    "Income certificate exceeded the limit"
                    if stage == ApplicationStage.rejected
                    else None
                ),
            )
            session.add(app)
            session.flush()
            ref_counter += 1
            total += 1
            if make_stuck:
                stuck += 1

            # Walk the history up to the current stage, oldest first.
            order = [
                ApplicationStage.form_filled,
                ApplicationStage.verified_signed,
                ApplicationStage.submitted,
                ApplicationStage.received,
                ApplicationStage.money_credited,
            ]
            if stage == ApplicationStage.rejected:
                path = order[: rng.randint(1, 3)] + [ApplicationStage.rejected]
            else:
                path = order[: order.index(stage) + 1]

            event_date = NOW - timedelta(days=days_in_stage + 20 * len(path))
            previous = None
            for st in path:
                session.add(
                    ApplicationStageEvent(
                        application_id=app.id,
                        from_stage=previous,
                        to_stage=st,
                        occurred_at=event_date,
                        changed_by_user_id=rng.choice(officers).id,
                        note=None,
                    )
                )
                previous = st
                event_date += timedelta(days=rng.randint(8, 30))

    session.flush()
    return total, stuck


def create_interactions(session: Session, families: list[Family], users: dict) -> int:
    """Calls, voice notes and visits, using the sample transcripts."""
    colonel = users["colonel"]
    officers = users["officers"]
    volunteers = users["volunteers"]
    count = 0

    for family in families:
        for _ in range(rng.randint(0, 4)):
            template = rng.choice(TRANSCRIPTS)
            widow_name = family.primary_contact_name.split()[0]
            child = next(
                (
                    m.full_name.split()[0]
                    for m in family.members
                    if m.relation in (Relation.son, Relation.daughter)
                ),
                "the child",
            )

            def fill(text: str | None) -> str | None:
                if text is None:
                    return None
                return text.replace("{widow}", widow_name).replace("{child}", child)

            if template["interaction_type"].value == "field_visit":
                author = rng.choice(volunteers)
            elif rng.random() < 0.6:
                author = colonel
            else:
                author = rng.choice(officers)

            # Talking points the system would have shown before a colonel's call.
            talking_points = []
            if author is colonel:
                talking_points = [
                    {
                        "type": "shared_posting",
                        "text": f"You and {family.soldier.full_name} were both at "
                        f"{rng.choice([p.place for p in family.soldier.postings]) if family.soldier.postings else 'Leh'}.",
                    },
                    {
                        "type": "known_date",
                        "text": f"Date of death: {family.soldier.date_of_death.strftime('%d-%m-%Y') if family.soldier.date_of_death else 'not recorded'}.",
                    },
                    {
                        "type": "unit",
                        "text": f"Served with {family.soldier.regiment}.",
                    },
                ]

            session.add(
                Interaction(
                    family_id=family.id,
                    interaction_type=template["interaction_type"],
                    occurred_at=NOW - timedelta(days=rng.randint(1, 500), hours=rng.randint(0, 20)),
                    by_user_id=author.id,
                    duration_seconds=rng.randint(90, 900),
                    language=template["language"],
                    transcript_original=fill(template["original"]),
                    transcript_english=fill(template["english"]),
                    summary_english=fill(template["summary"]),
                    extracted_fields=template["extracted"],
                    talking_points_used=talking_points,
                    sentiment=template["sentiment"],
                    follow_up_needed=template["follow_up"],
                    follow_up_note=template["follow_up_note"],
                )
            )
            count += 1

    session.flush()
    return count


def create_philanthropists(session: Session, families: list[Family]) -> tuple[int, int]:
    people = [
        ("Ashok Mehta", "Mehta Industries Pvt Ltd", "Mumbai",
         [PhilanthropistInterest.education], ["Maharashtra", "Punjab"], 2500000, 100000),
        ("Dr. Kavitha Raghavan", "Raghavan Medical Trust", "Chennai",
         [PhilanthropistInterest.medical], ["Tamil Nadu", "Kerala"], 1800000, 150000),
        ("Harbans Singh Chadha", None, "Ludhiana",
         [PhilanthropistInterest.marriage, PhilanthropistInterest.education],
         ["Punjab", "Haryana"], 1200000, 100000),
        ("Nalini Banerjee", "Banerjee Family Foundation", "Kolkata",
         [PhilanthropistInterest.education, PhilanthropistInterest.livelihood],
         ["West Bengal", "Bihar"], 900000, 75000),
        ("Rakesh Agarwal", "Agarwal Steels", "Delhi",
         [PhilanthropistInterest.livelihood], ["Haryana", "Uttar Pradesh", "Rajasthan"],
         3000000, 200000),
        ("Lt Gen (Retd) S. P. Malhotra", None, "Chandigarh",
         [PhilanthropistInterest.education, PhilanthropistInterest.medical],
         ["Punjab", "Himachal Pradesh", "Haryana"], 600000, 60000),
        ("Meera Pillai", "Pillai Charitable Trust", "Kochi",
         [PhilanthropistInterest.education], ["Kerala"], 750000, 50000),
        ("Suresh Patil", "Patil Agro Exports", "Pune",
         [PhilanthropistInterest.livelihood, PhilanthropistInterest.marriage],
         ["Maharashtra"], 1500000, 125000),
        ("Anand Krishnamurthy", "AK Tech Solutions", "Bengaluru",
         [PhilanthropistInterest.education], ["Tamil Nadu", "Karnataka"], 2000000, 150000),
        ("Shalini Rathore", None, "Jaipur",
         [PhilanthropistInterest.marriage], ["Rajasthan"], 500000, 100000),
        ("Jasbir Kaur Gill", "Gill Foundation", "Amritsar",
         [PhilanthropistInterest.medical, PhilanthropistInterest.livelihood],
         ["Punjab"], 850000, 70000),
        ("Tapan Dutta", None, "Siliguri",
         [PhilanthropistInterest.education], ["West Bengal"], 400000, 40000),
    ]

    created = []
    for name, org, city, interests, states, budget, per_family in people:
        p = Philanthropist(
            full_name=name,
            organisation=org,
            email=f"{name.split()[0].lower()}@mockdonor.example",
            phone=fake_phone(),
            city=city,
            interests=[i.value for i in interests],
            preferred_states=states,
            annual_budget=budget,
            max_per_family=per_family,
            wants_anonymity=rng.random() < 0.3,
        )
        session.add(p)
        created.append((p, interests, states, per_family))
    session.flush()

    # Propose matches where the donor's interest and preferred state line up.
    needs = {
        PhilanthropistInterest.education: "Education fees for a studying child",
        PhilanthropistInterest.medical: "Ongoing medical treatment costs",
        PhilanthropistInterest.marriage: "Daughter's marriage expenses",
        PhilanthropistInterest.livelihood: "Setting up a small home business",
    }
    match_count = 0
    for p, interests, states, per_family in created:
        eligible_families = [f for f in families if f.state in states]
        if not eligible_families:
            continue
        for family in rng.sample(
            eligible_families, k=min(len(eligible_families), rng.randint(2, 6))
        ):
            interest = rng.choice(interests)
            amount = rng.choice([25000, 40000, 50000, 75000, 100000])
            amount = min(amount, per_family)
            session.add(
                PhilanthropistMatch(
                    philanthropist_id=p.id,
                    family_id=family.id,
                    need_category=interest.value,
                    need_description=needs[interest],
                    amount_requested=amount,
                    amount_pledged=amount if rng.random() < 0.45 else None,
                    status=rng.choices(
                        ["proposed", "accepted", "declined", "funded"],
                        weights=[45, 22, 10, 23],
                    )[0],
                    match_score=rng.randint(55, 98),
                    match_reasons=[
                        f"Donor supports {interest.value}",
                        f"Family is in {family.state}, a preferred state",
                    ],
                    pledged_on=TODAY - timedelta(days=rng.randint(10, 400))
                    if rng.random() < 0.45
                    else None,
                )
            )
            match_count += 1

    session.flush()
    return len(created), match_count


def plant_data_problems(session: Session, families: list[Family]) -> int:
    """Break about 10% of records on purpose, and log each problem found.

    This is what the "needs attention" list is built from.
    """
    issues = 0

    def log(family, entity_type, entity_id, code, severity, description, field=None, details=None):
        nonlocal issues
        session.add(
            DataQualityIssue(
                entity_type=entity_type,
                entity_id=entity_id,
                family_id=family.id if family else None,
                issue_code=code,
                severity=severity,
                status=IssueStatus.open,
                field_name=field,
                description=description,
                details=details or {},
                detected_at=NOW - timedelta(days=rng.randint(0, 40)),
            )
        )
        issues += 1

    pool = rng.sample(families, 13)

    # 1. Missing phone numbers
    for family in pool[0:3]:
        family.primary_phone = None
        family.alternate_phone = None
        log(family, "family", family.id, IssueCode.missing_phone, IssueSeverity.high,
            "No phone number on record - this family cannot be contacted.", "primary_phone")

    # 2. Badly formatted phone numbers (how they often arrive from Excel)
    for family in pool[3:5]:
        family.primary_phone = rng.choice(["98765 4321", "0-9812345", "91-98 76 54"])
        log(family, "family", family.id, IssueCode.invalid_phone, IssueSeverity.high,
            f"Phone number '{family.primary_phone}' is not a valid +91 number.", "primary_phone")

    # 3. Missing date of death
    for family in pool[5:6]:
        family.soldier.date_of_death = None
        log(family, "soldier", family.soldier.id, IssueCode.missing_date_of_death,
            IssueSeverity.high, "Date of death is blank - eligibility cannot be calculated.",
            "date_of_death")

    # 4. Impossible dates: died before enrolment
    for family in pool[6:8]:
        soldier = family.soldier
        if soldier.date_of_enrolment:
            soldier.date_of_death = soldier.date_of_enrolment - timedelta(days=rng.randint(100, 900))
            log(family, "soldier", soldier.id, IssueCode.invalid_date, IssueSeverity.high,
                "Date of death is earlier than the date of enrolment.", "date_of_death",
                {"date_of_death": str(soldier.date_of_death),
                 "date_of_enrolment": str(soldier.date_of_enrolment)})

    # 5. Missing address
    for family in pool[8:9]:
        family.address_line = None
        family.village_or_town = None
        family.pincode = None
        family.location = None
        family.gps_coordinates = None
        log(family, "family", family.id, IssueCode.missing_address, IssueSeverity.medium,
            "No address on record - family will not appear on the map.", "address_line")

    # 6. Missing bank details - money cannot be credited
    for family in pool[9:11]:
        family.bank_account_number = None
        family.bank_ifsc = None
        family.bank_name = None
        log(family, "family", family.id, IssueCode.missing_bank_details, IssueSeverity.high,
            "No bank details - approved grants cannot be credited.", "bank_account_number")

    # 7. Information that has gone stale
    for family in pool[11:13]:
        family.last_verified_on = TODAY - timedelta(days=rng.randint(900, 1800))
        family.last_contacted_on = TODAY - timedelta(days=rng.randint(700, 1500))
        log(family, "family", family.id, IssueCode.outdated_information, IssueSeverity.medium,
            f"Details last verified on {family.last_verified_on.strftime('%d-%m-%Y')} - over two years ago.",
            "last_verified_on")

    # 8. Missing documents
    for family in rng.sample(families, 3):
        log(family, "family", family.id, IssueCode.missing_document, IssueSeverity.medium,
            "Death certificate has not been received.", None,
            {"document_type": "death_certificate"})

    session.flush()
    return issues


def plant_duplicates(session: Session, families: list[Family], colonel_career: list) -> int:
    """Create near-duplicate records, the way a re-imported Excel sheet would.

    They are flagged, never merged - how to merge them is still an open
    decision, so the system only raises the question for an officer.
    """
    originals = rng.sample(families, DUPLICATE_PAIRS)
    made = 0

    for i, original in enumerate(originals):
        orig_soldier = original.soldier
        # Same person, slightly different spelling and a different service number format.
        name_variant = orig_soldier.full_name.replace("aa", "a") if "aa" in orig_soldier.full_name else orig_soldier.full_name + " "
        name_variant = name_variant.strip().replace("Singh", "Sing") if rng.random() < 0.5 else orig_soldier.full_name.upper()

        dup_soldier = Soldier(
            full_name=name_variant,
            rank=orig_soldier.rank,
            service_number=(orig_soldier.service_number or "")[:-1] if orig_soldier.service_number else None,
            regiment=orig_soldier.regiment,
            unit=orig_soldier.unit,
            date_of_birth=orig_soldier.date_of_birth,
            date_of_enrolment=orig_soldier.date_of_enrolment,
            date_of_death=orig_soldier.date_of_death,
            cause_category=orig_soldier.cause_category,
            cause_sub_category=orig_soldier.cause_sub_category,
            place_of_death=orig_soldier.place_of_death,
            district_of_death=orig_soldier.district_of_death,
            state_of_death=orig_soldier.state_of_death,
            weather_at_death=orig_soldier.weather_at_death,
            duty_status=orig_soldier.duty_status,
            notes="Possible duplicate record created by a re-import.",
        )
        session.add(dup_soldier)
        session.flush()

        dup_family = Family(
            family_code=f"AP-{TODAY.year}-D{i + 1:03d}",
            soldier_id=dup_soldier.id,
            primary_contact_name=original.primary_contact_name.upper(),
            primary_phone=original.primary_phone,
            preferred_language=original.preferred_language,
            district=original.district,
            state=original.state,
            address_line=original.address_line,
            village_or_town=original.village_or_town,
            pincode=original.pincode,
            annual_income=original.annual_income,
            last_verified_on=TODAY - timedelta(days=rng.randint(400, 1000)),
        )
        session.add(dup_family)
        session.flush()

        session.add(
            FamilyMember(
                family_id=dup_family.id,
                full_name=dup_family.primary_contact_name,
                relation=Relation.widow,
                gender="female",
            )
        )

        for fam, other in ((dup_family, original), (original, dup_family)):
            session.add(
                DataQualityIssue(
                    entity_type="family",
                    entity_id=fam.id,
                    family_id=fam.id,
                    issue_code=IssueCode.possible_duplicate,
                    severity=IssueSeverity.high,
                    status=IssueStatus.open,
                    description=(
                        f"Looks like the same family as {other.family_code} "
                        f"({other.primary_contact_name}). Needs an officer to decide."
                    ),
                    details={
                        "other_family_id": other.id,
                        "other_family_code": other.family_code,
                        "matched_on": ["primary_phone", "district", "date_of_death"],
                    },
                    detected_at=NOW - timedelta(days=rng.randint(0, 30)),
                )
            )
        made += 1

    session.flush()
    return made


def create_history(session: Session, families: list[Family], users: dict) -> tuple[int, int]:
    """Field-level history and an audit trail, so nothing looks like it appeared from nowhere."""
    colonel = users["colonel"]
    officers = users["officers"]
    all_staff = [colonel, users["admin"], *officers, *users["volunteers"]]

    history = 0
    for family in families:
        # Every family was first created by the Excel import.
        session.add(
            FieldHistory(
                entity_type="family",
                entity_id=family.id,
                field_name="__created__",
                old_value=None,
                new_value=family.family_code,
                source=ChangeSource.excel_import,
                source_reference="widows_master_sheet_2024.xlsx",
                changed_at=NOW - timedelta(days=rng.randint(400, 900)),
                changed_by_user_id=users["admin"].id,
                note="Imported from the original Excel sheet.",
            )
        )
        history += 1

        for _ in range(rng.randint(0, 3)):
            field, old, new, source = rng.choice(
                [
                    ("primary_phone", fake_phone(), family.primary_phone, ChangeSource.phone_call),
                    ("annual_income", str(rng.randint(50000, 300000)),
                     str(family.annual_income), ChangeSource.officer_entry),
                    ("address_line", "Old village address", family.address_line,
                     ChangeSource.voice_note),
                    ("bank_ifsc", "SBIN0001234", family.bank_ifsc, ChangeSource.document_ocr),
                    ("preferred_language", "hindi", family.preferred_language.value,
                     ChangeSource.whatsapp),
                ]
            )
            session.add(
                FieldHistory(
                    entity_type="family",
                    entity_id=family.id,
                    field_name=field,
                    old_value=old,
                    new_value=str(new) if new is not None else None,
                    source=source,
                    changed_at=NOW - timedelta(days=rng.randint(1, 380)),
                    changed_by_user_id=rng.choice(all_staff).id,
                )
            )
            history += 1

    audit = 0
    actions = [
        "family.view", "family.update", "document.approve", "application.advance",
        "interaction.create", "export.download", "eligibility.recalculate",
    ]
    for _ in range(400):
        family = rng.choice(families)
        session.add(
            AuditLog(
                user_id=rng.choice(all_staff).id,
                action=rng.choice(actions),
                entity_type="family",
                entity_id=family.id,
                occurred_at=NOW - timedelta(days=rng.randint(0, 200), minutes=rng.randint(0, 1400)),
                details={"family_code": family.family_code},
                ip_address=f"10.0.{rng.randint(0, 5)}.{rng.randint(2, 250)}",
            )
        )
        audit += 1

    session.flush()
    return history, audit


# --- entry point --------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Army Passion mock database.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete all existing rows first."
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.reset:
            print("Clearing existing data...")
            reset(session)

        existing = session.query(Family).count()
        if existing:
            print(
                f"The database already has {existing} families. "
                "Re-run with --reset to rebuild from scratch."
            )
            return

        print("Creating users and the colonel's postings...")
        users = create_users(session)

        print("Creating MOCK schemes...")
        schemes = create_schemes(session)

        print(f"Creating {TOTAL_FAMILIES} soldiers and families...")
        # Roughly 18 of them follow the winter-fog two-wheeler pattern.
        fog_indexes = set(rng.sample(range(TOTAL_FAMILIES - DUPLICATE_PAIRS), 18))
        families: list[Family] = []
        for i in range(TOTAL_FAMILIES - DUPLICATE_PAIRS):
            _, family = build_soldier_and_family(
                session, i, users["colonel_career"], force_fog_accident=i in fog_indexes
            )
            families.append(family)

        print("Planting children who turn 18 within three months...")
        turning_18 = add_children_turning_18(session, families)

        print("Planting near-duplicate records...")
        duplicates = plant_duplicates(session, families, users["colonel_career"])

        print("Creating documents...")
        documents = create_documents(session, families, users["officers"])

        print("Creating applications and their stage history...")
        applications, stuck = create_applications(session, families, schemes, users)

        print("Creating call notes and voice-note transcripts...")
        interactions = create_interactions(session, families, users)

        print("Creating philanthropists and proposed matches...")
        donors, matches = create_philanthropists(session, families)

        print("Planting deliberate data-quality problems...")
        issues = plant_data_problems(session, families)

        print("Writing field history and audit log...")
        history, audit = create_history(session, families, users)

        session.commit()

        print("\n--- Done. What is now in the database ---")
        print(f"  Users                     {session.query(User).count()}")
        print(f"  MOCK schemes              {len(schemes)}")
        print(f"  Soldiers                  {session.query(Soldier).count()}")
        print(f"  Families                  {session.query(Family).count()}  (incl. {duplicates} planted duplicates)")
        print(f"  Family members            {session.query(FamilyMember).count()}")
        print(f"    turning 18 in 3 months  {turning_18}")
        print(f"  Postings                  {session.query(Posting).count()}")
        print(f"  Documents                 {documents}")
        print(f"  Applications              {applications}  ({stuck} stuck too long)")
        print(f"  Interactions              {interactions}")
        print(f"  Philanthropists           {donors}  ({matches} proposed matches)")
        print(f"  Data-quality issues       {session.query(DataQualityIssue).count()}")
        print(f"  Field history rows        {history}")
        print(f"  Audit log rows            {audit}")
        print("\nEligibility results are intentionally empty - the rules engine")
        print("is the next step and will fill that table itself.\n")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
