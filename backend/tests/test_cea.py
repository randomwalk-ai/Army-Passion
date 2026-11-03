"""The CEA rules, checked by hand-built families. No database needed.

Each test is one sentence of the circular, so a failing test says which rule
broke.
"""

from datetime import date

import pytest

from app.services.cea import (
    ELIGIBLE,
    ELIGIBLE_LATER,
    NEEDS_DATA,
    NOT_ELIGIBLE,
    AcademicYear,
    ChildInfo,
    class_number,
    default_definition,
    evaluate,
)

RULES = default_definition()["rules"]
YEAR = AcademicYear(2025)  # 01-04-2025 to 31-03-2026
DIED = date(2020, 6, 15)


def child(name: str, dob: date | None, cls: str | None = "Class 5", **kw) -> ChildInfo:
    return ChildInfo(member_id=None, name=name, dob=dob, class_text=cls, **kw)


def run(children, died=DIED, year=YEAR):
    return evaluate(children, died, year, RULES)


# --- academic years -----------------------------------------------------


def test_academic_year_runs_april_to_march():
    assert YEAR.label == "2025-26"
    assert YEAR.starts_on == date(2025, 4, 1)
    assert YEAR.ends_on == date(2026, 3, 31)
    assert len(YEAR.months()) == 12


def test_the_year_to_claim_is_the_last_one_that_ended():
    assert AcademicYear.last_completed(date(2026, 11, 3)).label == "2025-26"
    assert AcademicYear.last_completed(date(2026, 2, 1)).label == "2024-25"


def test_academic_year_parses_both_ways_of_writing_it():
    assert AcademicYear.parse("2023-24").start_year == 2023
    assert AcademicYear.parse("2023-2024").start_year == 2023
    with pytest.raises(ValueError):
        AcademicYear.parse("last year")


# --- reading a class ------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Class 8", 8), ("8th", 8), ("Std. 10", 10), ("XII", 12), ("class ix", 9),
        ("UKG", 0), ("Nursery", 0), ("KG", 0),
        ("B.A. 1st year", 13), ("ITI", 13), ("Diploma", 13), ("Graduate", 13),
        ("Not studying", -1), ("", None), (None, None), ("good student", None),
    ],
)
def test_class_is_read_the_way_sheets_write_it(text, expected):
    assert class_number(text) == expected


# --- the rules ------------------------------------------------------------


def test_two_eldest_school_children_can_claim_the_full_year():
    v = run([child("Asha", date(2012, 5, 1), "Class 8"), child("Ravi", date(2015, 1, 1), "Class 5")])
    assert v.status == ELIGIBLE
    assert [c.status for c in v.children] == [ELIGIBLE, ELIGIBLE]
    # 2025-26 is all at the 2024 rate: 12 x 2,813.
    assert v.children[0].cea_amount == 12 * 2813
    assert v.total == 2 * 12 * 2813


def test_only_the_two_eldest_count_even_if_the_eldest_has_left_school():
    v = run([
        child("Eldest", date(2000, 1, 1), "Graduate"),
        child("Second", date(2012, 1, 1), "Class 8"),
        child("Third", date(2014, 1, 1), "Class 6"),
    ])
    by_name = {c.name: c for c in v.children}
    assert by_name["Eldest"].status == NOT_ELIGIBLE
    assert by_name["Second"].status == ELIGIBLE
    assert by_name["Third"].status == NOT_ELIGIBLE
    assert "child no. 3" in by_name["Third"].reasons[0]


def test_children_are_ranked_by_date_of_birth_not_by_list_order():
    v = run([
        child("Youngest", date(2016, 1, 1), "Class 3"),
        child("Eldest", date(2011, 1, 1), "Class 9"),
        child("Middle", date(2013, 1, 1), "Class 7"),
    ])
    assert {c.name for c in v.eligible_children} == {"Eldest", "Middle"}


def test_over_twenty_at_the_start_of_the_year_cannot_claim():
    v = run([child("Old", date(2004, 3, 1), "Class 12")])  # 21 on 01-04-2025
    assert v.status == NOT_ELIGIBLE
    assert "limit is 20" in v.children[0].reasons[0]


def test_beyond_class_12_cannot_claim():
    v = run([child("College", date(2006, 1, 1), "B.Sc. 2nd year")])
    assert v.status == NOT_ELIGIBLE


def test_not_studying_cannot_claim():
    v = run([child("Home", date(2012, 1, 1), "Class 8", is_studying=False)])
    assert v.status == NOT_ELIGIBLE


def test_too_young_for_school_can_claim_later():
    v = run([child("Baby", date(2023, 6, 1), None)])
    assert v.status == ELIGIBLE_LATER
    assert v.becomes_eligible_on == date(2026, 6, 1)


def test_a_class_that_does_not_fit_the_age_is_questioned_not_decided():
    v = run([child("Typo", date(2018, 1, 1), "Class 10")])  # age 7
    assert v.status == NEEDS_DATA
    v = run([child("Typo", date(2016, 1, 1), "B.Tech 1st year")])  # age 9
    assert v.status == NEEDS_DATA


def test_unknown_class_is_counted_but_flagged_for_checking():
    v = run([child("Unsure", date(2014, 1, 1), None)])
    assert v.status == ELIGIBLE
    assert any("Class not recorded" in note for note in v.children[0].to_confirm)


def test_missing_date_of_birth_needs_data():
    v = run([child("NoDob", None)])
    assert v.status == NEEDS_DATA


def test_missing_date_of_death_needs_data():
    v = run([child("Asha", date(2012, 1, 1))], died=None)
    assert v.status == NEEDS_DATA


def test_soldier_who_died_after_the_year_gives_no_claim_for_it():
    v = run([child("Asha", date(2012, 1, 1))], died=date(2026, 5, 1))
    assert v.status == NOT_ELIGIBLE


def test_death_during_the_year_counts_from_that_month():
    v = run([child("Asha", date(2012, 1, 1), "Class 8")], died=date(2025, 10, 20))
    # October 2025 to March 2026 = 6 months.
    assert v.children[0].months == 6
    assert v.children[0].cea_amount == 6 * 2813


def test_hostel_is_paid_on_top():
    v = run([child("Hostel", date(2012, 1, 1), "Class 8", is_hostel=True)])
    assert v.children[0].hostel_amount == 12 * 8438
    assert v.total == 12 * (2813 + 8438)


def test_divyang_child_gets_the_divyang_rate():
    v = run([child("Special", date(2012, 1, 1), "Class 8", has_disability=True)])
    assert v.children[0].cea_amount == 12 * 5625


def test_a_year_across_the_rate_change_uses_both_rates():
    v = run([child("Asha", date(2012, 1, 1), "Class 6")], year=AcademicYear(2023))
    # April-December 2023 at 2,250, January-March 2024 at 2,813.
    assert v.children[0].cea_amount == 9 * 2250 + 3 * 2813


def test_years_before_2017_18_are_not_covered():
    v = run([child("Asha", date(2008, 1, 1), "Class 6")], year=AcademicYear(2016))
    assert v.status == NOT_ELIGIBLE


def test_no_children_cannot_claim():
    assert run([]).status == NOT_ELIGIBLE


def test_rules_come_from_the_data_not_the_code():
    """Change the limit in the rules and the verdict follows."""
    three = dict(RULES, eldest_children=3)
    kids = [
        child("A", date(2010, 1, 1), "Class 10"),
        child("B", date(2012, 1, 1), "Class 8"),
        child("C", date(2014, 1, 1), "Class 6"),
    ]
    assert len(evaluate(kids, DIED, YEAR, RULES).eligible_children) == 2
    assert len(evaluate(kids, DIED, YEAR, three).eligible_children) == 3
