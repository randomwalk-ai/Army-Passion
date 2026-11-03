"""The column guesser must be predictable. Same sheet in, same guess out."""

from app.services.column_mapping import (
    IGNORE,
    guess_column,
    guess_mapping,
    normalise,
    unmapped_required_fields,
)


def test_normalise_ignores_punctuation_and_case():
    assert normalise("Bank A/c No.") == "bank a c no"
    assert normalise("  DISTT  ") == "distt"
    assert normalise("Annual Income (Rs)") == "annual income rs"


def test_recognises_the_headings_an_office_sheet_actually_uses():
    cases = {
        "Name of Widow": "widow_name",
        "Husband Name": "soldier_name",
        "Date of Casualty": "date_of_death",
        "Mob No": "phone",
        "Distt": "district",
        "Regt / Unit": "unit",
        "Army No": "service_number",
        "Bank A/c No": "bank_account_number",
        "IFSC": "bank_ifsc",
        "No of Children": "children_count",
        "Remarks": "notes",
        "PIN": "pincode",
    }
    for heading, expected in cases.items():
        guess = guess_column(heading, [], 0)
        assert guess.target_key == expected, f"{heading} -> {guess.target_key}"
        assert guess.confidence >= 75


def test_row_numbers_are_skipped():
    for heading in ("S.No", "Sr No", "Sl No"):
        assert guess_column(heading, ["1", "2", "3"], 0).target_key == IGNORE


def test_falls_back_to_reading_the_values():
    """An unhelpful heading, but the values give it away."""
    phones = guess_column("Column 9", ["9876543210", "8123456789", "7012345678"], 8)
    assert phones.target_key == "phone"

    ifsc = guess_column("Code", ["SBIN0001234", "PUNB0345678", "CNRB0999111"], 3)
    assert ifsc.target_key == "bank_ifsc"

    pins = guess_column("Col", ["110001", "560034", "482001"], 2)
    assert pins.target_key == "pincode"


def test_unknown_column_is_left_for_him_to_decide():
    guess = guess_column("Zone Code", ["A", "B", "C"], 0)
    assert guess.target_key is None
    assert guess.confidence == 0


def test_two_columns_cannot_claim_the_same_field():
    headers = ["Mobile No", "Contact No"]
    samples = [["9876543210"], ["9812345678"]]
    guesses = guess_mapping(headers, samples)
    claimed = [g.target_key for g in guesses if g.target_key == "phone"]
    assert len(claimed) == 1, "the same field was mapped twice"


def test_missing_required_fields_are_reported():
    guesses = guess_mapping(["Mob No", "Distt"], [[], []])
    missing = {f.key for f in unmapped_required_fields(guesses)}
    assert "widow_name" in missing
    assert "soldier_name" in missing


def test_guessing_is_repeatable():
    headers = ["S.No", "Name of Widow", "Mob No", "Zone Code"]
    samples = [["1"], ["Sunita Devi"], ["9876543210"], ["X"]]
    first = [g.target_key for g in guess_mapping(headers, samples)]
    second = [g.target_key for g in guess_mapping(headers, samples)]
    assert first == second
