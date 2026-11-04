"""Suggested questions on the Assistant screen, built from today's data.

Ten types of suggestion. Each day five are shown: three "general" ones with a
count ("38 applications stuck") and two "specific" ones that name a person
("Mita Roy hasn't been contacted since 07-06-2023").

How the five are chosen:
- Stuck applications are always shown while there are any; they are the most urgent.
- The date picks the rest, so the set changes each morning but stays the same
  all day (easy to come back to after a phone call).
- No type shown yesterday is shown today, so two days never look alike.
- A type with nothing to show is skipped and another takes its place.
- Specific types rotate through their top five people, one per day.

The answers come from our own searches below, not from the LLM: they are
instant, free, and always agree with the number on the card.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Family
from app.services.ask import Answer, _cell, error
from app.services.cea import AcademicYear, ELIGIBLE, ensure_cea_scheme, evaluate_family

HOW_MANY = 5
GENERAL_PER_DAY = 3
SPECIFIC_PER_DAY = 2
# Specific types cycle through this many people, one per day.
ROTATE_TOP = 5
# The day-by-day choice is worked out from this date onwards, so every day's
# set knows exactly what the day before showed.
EPOCH = date(2020, 1, 1)

STAGE_NAMES = {
    "form_filled": "form filled",
    "verified_signed": "verified / signed",
    "submitted": "submitted",
    "received": "received",
}


@dataclass
class Suggestion:
    key: str
    group: str  # "general" or "specific"
    text: str
    count: int | None = None


def _dmy(day: date) -> str:
    return day.strftime("%d-%m-%Y")


def _rows(session: Session, sql: str, **params: Any) -> list[Any]:
    return list(session.execute(text(sql), params))


def _table(title: str, result: Any) -> Answer:
    columns = list(result.keys())
    rows = [[_cell(v) for v in row] for row in result]
    return Answer(kind="table", title=title, columns=columns, rows=rows, count=len(rows))


def _rank(today: date, how_many: int) -> int:
    """Which of the top people a specific suggestion shows today."""
    return today.toordinal() % min(ROTATE_TOP, how_many)


# --- the searches ---------------------------------------------------------------

STUCK = """
    FROM applications a
    JOIN families f ON f.id = a.family_id
    JOIN schemes s ON s.id = a.scheme_id
    WHERE NOT f.is_draft
      AND a.stage NOT IN ('money_credited', 'rejected')
      AND (:today - a.stage_changed_on) > a.stuck_after_days
"""

TURNING_18 = """
    FROM family_members m
    JOIN families f ON f.id = m.family_id
    WHERE NOT f.is_draft
      AND m.relation IN ('son', 'daughter')
      AND m.date_of_birth + interval '18 years' > :today
      AND m.date_of_birth + interval '18 years' <= :today + 90
"""

MISSING = """
    FROM data_quality_issues i
    JOIN families f ON f.id = i.family_id
    WHERE NOT f.is_draft AND i.status = 'open'
"""


def stuck_count(session: Session, today: date) -> int:
    return _rows(session, f"SELECT count(*) {STUCK}", today=today)[0][0]


def stuck_card(session: Session, today: date) -> Suggestion | None:
    n = stuck_count(session, today)
    if not n:
        return None
    return Suggestion("stuck", "general", f"{n} applications stuck, longest waiting first", n)


def stuck_answer(session: Session, today: date) -> Answer:
    result = session.execute(
        text(f"""SELECT f.primary_contact_name AS "Widow / NOK", f.district AS "District",
                   s.name AS "Scheme", a.stage AS "Stage",
                   a.stage_changed_on AS "In this stage since",
                   (:today - a.stage_changed_on) AS "Days waiting",
                   f.primary_phone AS "Phone", f.family_code AS "Family code"
            {STUCK} ORDER BY "Days waiting" DESC"""),
        {"today": today},
    )
    answer = _table("Applications stuck, longest waiting first", result)
    for row in answer.rows:
        row[3] = STAGE_NAMES.get(row[3], row[3])
    return answer


def turning_18_card(session: Session, today: date) -> Suggestion | None:
    n = _rows(session, f"SELECT count(*) {TURNING_18}", today=today)[0][0]
    if not n:
        return None
    return Suggestion("turning_18", "general", f"{n} children turning 18 in the next 3 months", n)


def turning_18_answer(session: Session, today: date) -> Answer:
    result = session.execute(
        text(f"""SELECT m.full_name AS "Child", m.relation AS "Son / daughter",
                   m.date_of_birth AS "Date of birth",
                   (m.date_of_birth + interval '18 years')::date AS "Turns 18 on",
                   f.primary_contact_name AS "Widow / NOK", f.district AS "District",
                   f.primary_phone AS "Phone", f.family_code AS "Family code"
            {TURNING_18} ORDER BY "Turns 18 on" """),
        {"today": today},
    )
    return _table("Children turning 18 in the next 3 months", result)


def missing_card(session: Session, today: date) -> Suggestion | None:
    n = _rows(session, f"SELECT count(DISTINCT f.id) {MISSING}")[0][0]
    if not n:
        return None
    return Suggestion("missing", "general", f"{n} families with missing or wrong details", n)


def missing_answer(session: Session, today: date) -> Answer:
    result = session.execute(
        text(f"""SELECT f.primary_contact_name AS "Widow / NOK", f.district AS "District",
                   string_agg(DISTINCT replace(i.issue_code::text, '_', ' '), ', ') AS "What needs fixing",
                   f.primary_phone AS "Phone", f.family_code AS "Family code"
            {MISSING}
            GROUP BY f.id ORDER BY f.primary_contact_name""")
    )
    return _table("Families with missing or wrong details", result)


def _cea_families(session: Session, today: date) -> tuple[str, list[tuple[Family, Any]]]:
    """Families with at least one child who can claim CEA, as the CEA screen decides it."""
    scheme = ensure_cea_scheme(session)
    session.commit()
    year = AcademicYear.last_completed(today, scheme.rules.get("academic_year_start_month", 4))
    families = session.scalars(
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
        .order_by(Family.primary_contact_name)
    ).all()
    verdicts = [(f, evaluate_family(f, year, scheme.rules)) for f in families]
    return year.label, [(f, v) for f, v in verdicts if v.status == ELIGIBLE]


def cea_card(session: Session, today: date) -> Suggestion | None:
    label, eligible = _cea_families(session, today)
    if not eligible:
        return None
    n = len(eligible)
    return Suggestion("cea", "general", f"{n} families can claim CEA for {label}", n)


def cea_answer(session: Session, today: date) -> Answer:
    label, eligible = _cea_families(session, today)
    return Answer(
        kind="table",
        title=f"Families who can claim CEA for {label}",
        columns=["Widow / NOK", "District", "Children who can claim", "Phone", "Family code"],
        rows=[
            [f.primary_contact_name, f.district,
             ", ".join(c.name for c in v.eligible_children), f.primary_phone, f.family_code]
            for f, v in eligible
        ],
        count=len(eligible),
    )


def _birthdays(session: Session, today: date) -> list[tuple[date, Any]]:
    """Children whose birthday falls in the next 7 days (today included)."""
    children = _rows(
        session,
        """SELECT m.full_name, m.relation, m.date_of_birth, f.primary_contact_name,
                  f.district, f.primary_phone, f.family_code
           FROM family_members m JOIN families f ON f.id = m.family_id
           WHERE NOT f.is_draft AND m.relation IN ('son', 'daughter')
             AND m.date_of_birth IS NOT NULL""",
    )
    found = []
    for child in children:
        dob = child[2]
        for year in (today.year, today.year + 1):
            try:
                birthday = dob.replace(year=year)
            except ValueError:  # born on 29 February
                birthday = date(year, 3, 1)
            if today <= birthday <= today + timedelta(days=6):
                found.append((birthday, child))
                break
    return sorted(found, key=lambda pair: (pair[0], pair[1][0]))


def birthdays_card(session: Session, today: date) -> Suggestion | None:
    n = len(_birthdays(session, today))
    if not n:
        return None
    return Suggestion("birthdays", "general", f"{n} children have a birthday this week", n)


def birthdays_answer(session: Session, today: date) -> Answer:
    rows = [
        [c[0], c[1], _dmy(b), b.year - c[2].year, c[3], c[4], c[5], c[6]]
        for b, c in _birthdays(session, today)
    ]
    return Answer(
        kind="table",
        title="Children with a birthday this week",
        columns=["Child", "Son / daughter", "Birthday", "Turning", "Widow / NOK",
                 "District", "Phone", "Family code"],
        rows=rows,
        count=len(rows),
    )


# --- specific: one named person or place ------------------------------------------


def _next_18(session: Session, today: date) -> Any | None:
    top = _rows(
        session,
        """SELECT m.full_name, (m.date_of_birth + interval '18 years')::date AS turns,
                  f.id, f.primary_contact_name, f.district
           FROM family_members m JOIN families f ON f.id = m.family_id
           WHERE NOT f.is_draft AND m.relation IN ('son', 'daughter')
             AND m.date_of_birth + interval '18 years' >= :today
           ORDER BY turns, m.full_name LIMIT :top""",
        today=today, top=ROTATE_TOP,
    )
    return top[_rank(today, len(top))] if top else None


def next_18_card(session: Session, today: date) -> Suggestion | None:
    child = _next_18(session, today)
    if not child:
        return None
    return Suggestion(
        "next_18", "specific",
        f"{child[0]} turns 18 on {_dmy(child[1])}. Show the family ({child[3]}, {child[4]})",
    )


def next_18_answer(session: Session, today: date) -> Answer:
    child = _next_18(session, today)
    result = session.execute(
        text("""SELECT m.full_name AS "Name", m.relation AS "Relation",
                   m.date_of_birth AS "Date of birth",
                   date_part('year', age(:today, m.date_of_birth))::int AS "Age",
                   m.education_level AS "Education", f.primary_phone AS "Phone",
                   f.district AS "District"
            FROM family_members m JOIN families f ON f.id = m.family_id
            WHERE f.id = :family
            ORDER BY m.relation = 'widow' DESC, m.date_of_birth"""),
        {"today": today, "family": child[2]},
    )
    return _table(f"Family of {child[0]}, who turns 18 on {_dmy(child[1])}", result)


def _longest_stuck(session: Session, today: date) -> Any | None:
    top = _rows(
        session,
        f"""SELECT a.id, f.primary_contact_name, s.name, a.stage,
                   (:today - a.stage_changed_on) AS days, f.district
            {STUCK} ORDER BY days DESC, a.id LIMIT :top""",
        today=today, top=ROTATE_TOP,
    )
    return top[_rank(today, len(top))] if top else None


def longest_stuck_card(session: Session, today: date) -> Suggestion | None:
    app = _longest_stuck(session, today)
    if not app:
        return None
    scheme = app[2].removeprefix("MOCK ")
    return Suggestion(
        "longest_stuck", "specific",
        f"{app[1]}'s {scheme} has been stuck at “{STAGE_NAMES.get(app[3], app[3])}” "
        f"for {app[4]} days ({app[5]})",
    )


def longest_stuck_answer(session: Session, today: date) -> Answer:
    app = _longest_stuck(session, today)
    result = session.execute(
        text("""SELECT f.primary_contact_name AS "Widow / NOK", s.name AS "Scheme",
                   a.reference_code AS "Reference", a.stage AS "Stage",
                   a.stage_changed_on AS "In this stage since",
                   (:today - a.stage_changed_on) AS "Days waiting",
                   a.ksb_dak_id AS "KSB DAK ID", f.primary_phone AS "Phone",
                   f.district AS "District", f.family_code AS "Family code"
            FROM applications a JOIN families f ON f.id = a.family_id
            JOIN schemes s ON s.id = a.scheme_id WHERE a.id = :app"""),
        {"today": today, "app": app[0]},
    )
    answer = _table(f"{app[1]}'s application, stuck {app[4]} days", result)
    for row in answer.rows:
        row[3] = STAGE_NAMES.get(row[3], row[3])
    return answer


def _no_contact(session: Session, today: date) -> Any | None:
    # A family never contacted at all comes first.
    top = _rows(
        session,
        """SELECT f.id, f.primary_contact_name, f.district, f.last_contacted_on
           FROM families f WHERE NOT f.is_draft
           ORDER BY f.last_contacted_on NULLS FIRST, f.primary_contact_name LIMIT :top""",
        top=ROTATE_TOP,
    )
    return top[_rank(today, len(top))] if top else None


def no_contact_card(session: Session, today: date) -> Suggestion | None:
    fam = _no_contact(session, today)
    if not fam:
        return None
    when = f"since {_dmy(fam[3])}" if fam[3] else "yet"
    return Suggestion(
        "no_contact", "specific", f"{fam[1]} ({fam[2]}) hasn't been contacted {when}"
    )


def no_contact_answer(session: Session, today: date) -> Answer:
    fam = _no_contact(session, today)
    result = session.execute(
        text("""SELECT f.primary_contact_name AS "Widow / NOK", f.primary_phone AS "Phone",
                   f.alternate_phone AS "Other phone", f.preferred_language AS "Language",
                   f.village_or_town AS "Village", f.district AS "District",
                   f.last_contacted_on AS "Last contacted", f.family_code AS "Family code"
            FROM families f WHERE f.id = :family"""),
        {"family": fam[0]},
    )
    return _table(f"{fam[1]}: not contacted for the longest time", result)


def _top_district(session: Session, today: date) -> Any | None:
    top = _rows(
        session,
        """SELECT district, count(*) AS n FROM families
           WHERE NOT is_draft AND district IS NOT NULL
           GROUP BY district ORDER BY n DESC, district LIMIT :top""",
        top=ROTATE_TOP,
    )
    return top[_rank(today, len(top))] if top else None


def district_card(session: Session, today: date) -> Suggestion | None:
    place = _top_district(session, today)
    if not place:
        return None
    return Suggestion("district", "specific", f"{place[0]} has {place[1]} families. List them")


def district_answer(session: Session, today: date) -> Answer:
    place = _top_district(session, today)
    result = session.execute(
        text("""SELECT f.primary_contact_name AS "Widow / NOK", s.full_name AS "Soldier",
                   f.village_or_town AS "Village", f.primary_phone AS "Phone",
                   f.family_code AS "Family code"
            FROM families f JOIN soldiers s ON s.id = f.soldier_id
            WHERE NOT f.is_draft AND f.district = :district
            ORDER BY f.primary_contact_name"""),
        {"district": place[0]},
    )
    return _table(f"Families in {place[0]}", result)


def _latest_import(session: Session) -> tuple[str, list[int]] | None:
    """The last Excel import that added families, and which families it added."""
    rows = _rows(
        session,
        """SELECT source_reference, entity_id FROM field_history
           WHERE entity_type = 'family' AND field_name = '__created__'
             AND source_reference = (
               SELECT source_reference FROM field_history
               WHERE entity_type = 'family' AND field_name = '__created__'
                 AND source_reference LIKE 'import#%'
               ORDER BY changed_at DESC LIMIT 1)""",
    )
    if not rows:
        return None
    # "import#12 widows_sheet_oct.xlsx" -> "widows_sheet_oct.xlsx"
    filename = rows[0][0].split(" ", 1)[-1]
    return filename, [r[1] for r in rows]


def latest_import_card(session: Session, today: date) -> Suggestion | None:
    found = _latest_import(session)
    if not found:
        return None
    filename, ids = found
    return Suggestion(
        "latest_import", "specific",
        f"See the {len(ids)} families added from {filename}",
    )


def latest_import_answer(session: Session, today: date) -> Answer:
    filename, ids = _latest_import(session)
    result = session.execute(
        text("""SELECT f.primary_contact_name AS "Widow / NOK", f.district AS "District",
                   f.primary_phone AS "Phone", f.family_code AS "Family code"
            FROM families f WHERE f.id = ANY(:ids) ORDER BY f.primary_contact_name"""),
        {"ids": ids},
    )
    return _table(f"Families added from {filename}", result)


# --- the pool --------------------------------------------------------------------


@dataclass(frozen=True)
class SuggestionType:
    key: str
    group: str
    card: Callable[[Session, date], Suggestion | None]
    answer: Callable[[Session, date], Answer]


# The order matters only as a tie-break; the day decides the rest.
TYPES = [
    SuggestionType("stuck", "general", stuck_card, stuck_answer),
    SuggestionType("turning_18", "general", turning_18_card, turning_18_answer),
    SuggestionType("missing", "general", missing_card, missing_answer),
    SuggestionType("cea", "general", cea_card, cea_answer),
    SuggestionType("birthdays", "general", birthdays_card, birthdays_answer),
    SuggestionType("next_18", "specific", next_18_card, next_18_answer),
    SuggestionType("longest_stuck", "specific", longest_stuck_card, longest_stuck_answer),
    SuggestionType("no_contact", "specific", no_contact_card, no_contact_answer),
    SuggestionType("district", "specific", district_card, district_answer),
    SuggestionType("latest_import", "specific", latest_import_card, latest_import_answer),
]
BY_KEY = {t.key: t for t in TYPES}
ALWAYS = "stuck"
ROTATING_GENERAL = [t.key for t in TYPES if t.group == "general" and t.key != ALWAYS]
SPECIFIC = [t.key for t in TYPES if t.group == "specific"]


def planned_types(day: date) -> list[str]:
    """The rotating types planned for a day, before checking which have data.

    Worked out day by day from EPOCH so that each day can leave out exactly
    what the day before planned. The date seeds the choice, so the same day
    always gives the same answer.
    """
    start = min(EPOCH, day)
    yesterday: set[str] = set()
    plan: list[str] = []
    for n in range(start.toordinal(), day.toordinal() + 1):
        rng = random.Random(n)
        general = rng.sample(
            [k for k in ROTATING_GENERAL if k not in yesterday], GENERAL_PER_DAY - 1
        )
        specific = rng.sample([k for k in SPECIFIC if k not in yesterday], SPECIFIC_PER_DAY)
        plan = general + specific
        yesterday = set(plan)
    return plan


def todays_suggestions(session: Session, today: date | None = None) -> list[Suggestion]:
    today = today or date.today()
    plan = planned_types(today)
    yesterday = set(planned_types(today - timedelta(days=1)))

    cards: dict[str, Suggestion | None] = {}

    def card(key: str) -> Suggestion | None:
        if key not in cards:
            cards[key] = BY_KEY[key].card(session, today)
        return cards[key]

    chosen: list[Suggestion] = []
    urgent = card(ALWAYS)
    if urgent:
        chosen.append(urgent)

    # Today's plan first; for any planned type with nothing to show, a type
    # from the same group that was not shown yesterday, then any type at all.
    for key in plan:
        if (found := card(key)) and found not in chosen:
            chosen.append(found)
    spares = [t.key for t in TYPES if t.key not in plan and t.key != ALWAYS]
    spares.sort(key=lambda k: k in yesterday)  # not-yesterday first
    for key in spares:
        if len(chosen) >= HOW_MANY:
            break
        if found := card(key):
            chosen.append(found)
    return chosen[:HOW_MANY]


def answer_suggestion(session: Session, key: str, today: date | None = None) -> Answer:
    kind = BY_KEY.get(key)
    if kind is None:
        return error("I do not know that suggestion.")
    today = today or date.today()
    if kind.card(session, today) is None:
        return error("There is nothing to show for this any more.")
    return kind.answer(session, today)
