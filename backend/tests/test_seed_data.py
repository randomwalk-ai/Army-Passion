"""Checks that the mock database actually matches what the brief asked for.

These run against the seeded development database. If they fail, re-run:
    python -m seed.generate --reset
"""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.models import (
    Application,
    DataQualityIssue,
    Family,
    FamilyMember,
    Interaction,
    Philanthropist,
    Posting,
    Scheme,
    Soldier,
    User,
)
from app.models.enums import (
    ApplicationStage,
    IssueCode,
    Language,
    Relation,
    UserRole,
)

TODAY = date.today()


# --- volume -------------------------------------------------------------------


def test_about_150_families(db):
    count = db.scalar(select(func.count()).select_from(Family))
    assert 140 <= count <= 160, f"expected around 150 families, found {count}"


def test_every_family_has_a_soldier_and_a_widow(db):
    families = db.scalars(select(Family)).all()
    assert families
    for family in families:
        assert family.soldier is not None, f"{family.family_code} has no soldier"
        relations = {m.relation for m in family.members}
        assert Relation.widow in relations, f"{family.family_code} has no widow recorded"


# --- schemes ------------------------------------------------------------------


def test_eight_to_ten_schemes_all_clearly_mock(db):
    schemes = db.scalars(select(Scheme)).all()
    assert 8 <= len(schemes) <= 10
    for scheme in schemes:
        assert scheme.is_mock is True
        assert "MOCK" in scheme.name.upper()
        assert "MOCK" in scheme.code.upper()


def test_scheme_rules_are_stored_as_data(db):
    """Rules must be readable JSON with a known shape, never code."""
    allowed_ops = {
        "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "is_true", "is_false",
    }
    for scheme in db.scalars(select(Scheme)).all():
        assert isinstance(scheme.rules, dict) and scheme.rules
        assert set(scheme.rules) <= {"all", "any"}
        for conditions in scheme.rules.values():
            assert conditions, f"{scheme.code} has an empty rule group"
            for condition in conditions:
                assert set(condition) == {"field", "op", "value"}
                assert condition["op"] in allowed_ops
                assert isinstance(condition["field"], str) and condition["field"]


# --- data quality: the deliberate problems ------------------------------------


def test_roughly_ten_percent_of_families_have_problems(db):
    total = db.scalar(select(func.count()).select_from(Family))
    flagged = db.scalar(
        select(func.count(func.distinct(DataQualityIssue.family_id)))
    )
    share = flagged / total
    # The brief asks for problems in about 10% of records. A duplicate flags
    # both halves of the pair, so the figure sits a little above that.
    assert 0.08 <= share <= 0.18, f"{flagged}/{total} families flagged ({share:.0%})"


def test_each_kind_of_problem_is_present(db):
    found = set(
        db.scalars(select(DataQualityIssue.issue_code).distinct()).all()
    )
    for expected in (
        IssueCode.missing_phone,
        IssueCode.invalid_phone,
        IssueCode.invalid_date,
        IssueCode.missing_date_of_death,
        IssueCode.possible_duplicate,
        IssueCode.missing_document,
        IssueCode.outdated_information,
        IssueCode.missing_bank_details,
    ):
        assert expected in found, f"no {expected.value} issue was planted"


def test_duplicates_are_flagged_and_never_merged(db):
    """Both records in a duplicate pair must still exist, each pointing at the other."""
    issues = db.scalars(
        select(DataQualityIssue).where(
            DataQualityIssue.issue_code == IssueCode.possible_duplicate
        )
    ).all()
    assert issues, "no duplicates were planted"
    for issue in issues:
        other_id = issue.details.get("other_family_id")
        assert other_id is not None
        assert db.get(Family, other_id) is not None, "the other half of the pair was merged away"


def test_good_phone_numbers_are_indian_format(db):
    """Every phone that was not deliberately broken must be +91 plus ten digits."""
    broken = {
        i.family_id
        for i in db.scalars(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_code == IssueCode.invalid_phone
            )
        ).all()
    }
    for family in db.scalars(select(Family)).all():
        if family.id in broken or not family.primary_phone:
            continue
        phone = family.primary_phone
        assert phone.startswith("+91"), f"{family.family_code}: {phone}"
        assert len(phone) == 13 and phone[3:].isdigit(), f"{family.family_code}: {phone}"
        assert phone[3] in "6789", f"{family.family_code}: {phone}"


# --- the patterns the colonel needs to see ------------------------------------


def test_children_turn_18_within_three_months(db):
    """The 'becomes eligible later' alert needs these to exist."""
    eighteenth_from = TODAY - timedelta(days=18 * 365)
    soon = db.scalars(
        select(FamilyMember).where(
            FamilyMember.relation.in_([Relation.son, Relation.daughter]),
            FamilyMember.date_of_birth > eighteenth_from,
            FamilyMember.date_of_birth <= eighteenth_from + timedelta(days=95),
        )
    ).all()
    assert len(soon) >= 8, f"only {len(soon)} children turn 18 soon"


def test_winter_fog_two_wheeler_pattern_exists(db):
    """Winter two-wheeler deaths in the foggy Punjab/Haryana belt."""
    rows = db.scalars(
        select(Soldier).where(
            Soldier.cause_sub_category == "Two-wheeler road accident",
            Soldier.weather_at_death == "Dense fog",
            Soldier.state_of_death.in_(["Punjab", "Haryana"]),
        )
    ).all()
    assert len(rows) >= 10, f"only {len(rows)} fog-belt accidents"
    winter = [r for r in rows if r.date_of_death and r.date_of_death.month in (12, 1)]
    assert len(winter) >= 10, "the fog accidents are not concentrated in winter"


def test_some_applications_are_stuck(db):
    stuck = [
        a
        for a in db.scalars(select(Application)).all()
        if a.is_stuck(TODAY)
    ]
    assert len(stuck) >= 10, f"only {len(stuck)} stuck applications"


def test_applications_cover_every_stage(db):
    stages = set(db.scalars(select(Application.stage).distinct()).all())
    for stage in ApplicationStage:
        assert stage in stages, f"no application is at stage {stage.value}"


def test_credited_applications_have_an_amount_and_a_dak_id(db):
    credited = db.scalars(
        select(Application).where(Application.stage == ApplicationStage.money_credited)
    ).all()
    assert credited
    for app in credited:
        assert app.amount_credited and app.amount_credited > 0
        assert app.credited_on is not None
        assert app.ksb_dak_id is not None


def test_colonel_shares_postings_with_some_soldiers(db):
    """Talking points come from these overlaps, so there must be some."""
    colonel = db.scalar(select(User).where(User.role == UserRole.colonel))
    assert colonel is not None
    colonel_places = {
        (p.place, p.from_year, p.to_year)
        for p in db.scalars(select(Posting).where(Posting.user_id == colonel.id)).all()
    }
    assert colonel_places

    overlapping_soldiers = set()
    for posting in db.scalars(
        select(Posting).where(Posting.soldier_id.is_not(None))
    ).all():
        for place, c_from, c_to in colonel_places:
            if posting.place == place and posting.from_year <= c_to and posting.to_year >= c_from:
                overlapping_soldiers.add(posting.soldier_id)
                break

    assert len(overlapping_soldiers) >= 20, (
        f"only {len(overlapping_soldiers)} soldiers share a posting with the colonel"
    )


def test_weather_is_plausible_for_the_cause(db):
    """Insights are only useful if weather actually relates to how people died."""
    cold = {"Heavy snowfall", "Extreme cold"}
    for soldier in db.scalars(select(Soldier)).all():
        sub, weather = soldier.cause_sub_category, soldier.weather_at_death
        if sub in {"Avalanche", "Frostbite complications"}:
            assert weather in cold, f"{sub} recorded in '{weather}'"
        if sub == "Heat stroke on duty":
            assert weather == "Heat wave", f"{sub} recorded in '{weather}'"


def test_no_snowfall_in_the_tropical_south(db):
    southern = {"Tamil Nadu", "Kerala", "Telangana", "Karnataka"}
    for soldier in db.scalars(
        select(Soldier).where(Soldier.state_of_death.in_(southern))
    ).all():
        assert soldier.weather_at_death != "Heavy snowfall", (
            f"snowfall recorded in {soldier.state_of_death}"
        )


# --- language and translation -------------------------------------------------


def test_interactions_have_english_translations(db):
    interactions = db.scalars(select(Interaction)).all()
    assert interactions
    for item in interactions:
        assert item.transcript_english, "a transcript has no English translation"
        assert item.summary_english, "a transcript has no English summary"


def test_hindi_and_english_transcripts_both_exist(db):
    languages = set(db.scalars(select(Interaction.language).distinct()).all())
    assert Language.hindi in languages
    assert Language.english in languages
    assert len(languages) >= 4, "expected several Indian languages in the call notes"


def test_regional_languages_match_their_states(db):
    expected = {
        "Punjab": Language.punjabi,
        "Tamil Nadu": Language.tamil,
        "Kerala": Language.malayalam,
        "West Bengal": Language.bengali,
        "Maharashtra": Language.marathi,
    }
    for state, language in expected.items():
        families = db.scalars(select(Family).where(Family.state == state)).all()
        if not families:
            continue
        assert any(f.preferred_language == language for f in families), (
            f"no family in {state} prefers {language.value}"
        )


# --- map ----------------------------------------------------------------------


def test_most_families_have_coordinates(db):
    total = db.scalar(select(func.count()).select_from(Family))
    located = db.scalar(
        select(func.count()).select_from(Family).where(Family.location.is_not(None))
    )
    assert located / total >= 0.85, f"only {located}/{total} families can be mapped"


# --- philanthropists ----------------------------------------------------------


def test_philanthropists_have_interests_and_regions(db):
    donors = db.scalars(select(Philanthropist)).all()
    assert len(donors) >= 5
    allowed = {"education", "medical", "marriage", "livelihood"}
    for donor in donors:
        assert donor.interests and set(donor.interests) <= allowed
        assert donor.preferred_states


def test_matches_respect_the_donors_preferred_states(db):
    for donor in db.scalars(select(Philanthropist)).all():
        for match in donor.matches:
            family = db.get(Family, match.family_id)
            assert family.state in donor.preferred_states, (
                f"{donor.full_name} matched to a family in {family.state}, "
                f"which is not in {donor.preferred_states}"
            )
