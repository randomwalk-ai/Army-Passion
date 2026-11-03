"""Cleaning up the messy values an office sheet contains."""

from datetime import date

from app.models.enums import DeathCauseCategory, IssueCode
from app.services.row_parser import (
    parse_amount,
    parse_cause,
    parse_count,
    parse_date,
    parse_ifsc,
    parse_phone,
    parse_pincode,
    parse_row,
    tidy_name,
)


# --- phones -------------------------------------------------------------------


def test_phone_numbers_in_every_shape_become_one_format():
    for raw in ("9876543210", "+919876543210", "+91 98765 43210", "098765 43210",
                "98765-43210", "91-9876543210"):
        value, problem = parse_phone(raw)
        assert problem is None, f"{raw}: {problem}"
        assert value == "+919876543210", f"{raw} -> {value}"


def test_bad_phone_numbers_are_reported_not_guessed():
    for raw in ("98765 4321", "12345678901234", "0000000000", "5876543210"):
        value, problem = parse_phone(raw)
        assert value is None
        assert problem, f"{raw} should have been rejected"


def test_blank_phone_is_not_an_error_here():
    assert parse_phone("") == (None, None)


# --- dates --------------------------------------------------------------------


def test_dates_are_read_day_first():
    expected = date(2021, 3, 14)
    for raw in ("14-03-2021", "14/03/2021", "14.3.2021", "14 Mar 2021",
                "14 March 2021", "2021-03-14"):
        value, problem = parse_date(raw)
        assert problem is None, f"{raw}: {problem}"
        assert value == expected, f"{raw} -> {value}"


def test_two_digit_years_are_sensible():
    assert parse_date("14-03-21")[0] == date(2021, 3, 14)
    assert parse_date("14-03-95")[0] == date(1995, 3, 14)


def test_impossible_and_future_dates_are_refused():
    for raw in ("32-01-2021", "14-13-2021", "31-02-2021", "01-01-2099", "not a date"):
        value, problem = parse_date(raw)
        assert value is None, f"{raw} was accepted"
        assert problem


# --- other values -------------------------------------------------------------


def test_amounts_strip_currency_and_commas():
    assert parse_amount("1,20,000")[0] == 120000
    assert parse_amount("Rs. 95000")[0] == 95000
    assert parse_amount("120000.00")[0] == 120000
    assert parse_amount("")[0] is None


def test_counts_handle_nil():
    assert parse_count("3")[0] == 3
    assert parse_count("Nil")[0] == 0
    assert parse_count("two")[0] is None


def test_pincode_and_ifsc_are_validated():
    assert parse_pincode("110001")[0] == "110001"
    assert parse_pincode("11000")[0] is None
    assert parse_ifsc("sbin0001234")[0] == "SBIN0001234"
    assert parse_ifsc("SBIN1234")[0] is None


def test_shouting_names_are_tidied():
    assert tidy_name("SUNITA  DEVI") == "Sunita Devi"
    assert tidy_name("  kamlesh kaur ") == "Kamlesh Kaur"
    assert tidy_name("Ram Singh") == "Ram Singh"
    assert tidy_name("") is None


def test_free_text_causes_are_grouped():
    assert parse_cause("Killed in action")[0] == DeathCauseCategory.battle_casualty
    assert parse_cause("Road accident")[0] == DeathCauseCategory.accident
    assert parse_cause("Heart attack")[0] == DeathCauseCategory.illness
    assert parse_cause("Avalanche")[0] == DeathCauseCategory.physical_casualty
    # The original wording is always kept.
    assert parse_cause("Road accident")[1] == "Road accident"


# --- whole rows ---------------------------------------------------------------

HEADERS = ["S.No", "Name of Widow", "Husband Name", "Mob No", "Date of Casualty", "Distt"]
MAPPING = {
    "S.No": "__ignore__",
    "Name of Widow": "widow_name",
    "Husband Name": "soldier_name",
    "Mob No": "phone",
    "Date of Casualty": "date_of_death",
    "Distt": "district",
}


def test_a_good_row_parses_cleanly():
    row = ["1", "SUNITA DEVI", "Ram Singh", "9876543210", "14-03-2021", "Hisar"]
    parsed = parse_row(row, MAPPING, HEADERS, 4)
    assert parsed.values["widow_name"] == "Sunita Devi"
    assert parsed.values["phone"] == "+919876543210"
    assert parsed.values["date_of_death"] == date(2021, 3, 14)
    assert parsed.values["district"] == "Hisar"
    assert parsed.problems == []


def test_ignored_columns_are_not_stored():
    row = ["1", "Sunita Devi", "Ram Singh", "9876543210", "14-03-2021", "Hisar"]
    parsed = parse_row(row, MAPPING, HEADERS, 4)
    assert "__ignore__" not in parsed.values


def test_a_missing_phone_is_flagged():
    row = ["1", "Sunita Devi", "Ram Singh", "", "14-03-2021", "Hisar"]
    parsed = parse_row(row, MAPPING, HEADERS, 4)
    codes = {p.code for p in parsed.problems}
    assert IssueCode.missing_phone in codes


def test_a_bad_phone_is_flagged_and_not_stored():
    row = ["1", "Sunita Devi", "Ram Singh", "98765 4321", "14-03-2021", "Hisar"]
    parsed = parse_row(row, MAPPING, HEADERS, 4)
    assert "phone" not in parsed.values
    assert IssueCode.invalid_phone in {p.code for p in parsed.problems}


def test_a_row_with_no_names_cannot_become_a_family():
    row = ["1", "", "", "9876543210", "14-03-2021", "Hisar"]
    assert parse_row(row, MAPPING, HEADERS, 4).has_blocking_problem
