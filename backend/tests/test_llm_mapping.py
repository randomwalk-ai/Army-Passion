"""The LLM step: only the leftovers are sent, and only headings.

The rule being protected here: the LLM assists, it never takes over. It
cannot overrule a column the rules already matched, cannot invent a field,
and cannot create anything without the colonel confirming.
"""

import pytest

from app.services.column_mapping import (
    IGNORE,
    TARGET_BY_KEY,
    TARGET_FIELDS,
    ColumnGuess,
    apply_llm_suggestions,
    guess_mapping,
)
from app.services.llm import (
    GeminiLLM,
    HeadingSuggestion,
    MockLLM,
    build_prompt,
    parse_response,
)

FIELDS = [(f.key, f.label) for f in TARGET_FIELDS]
VALID = set(TARGET_BY_KEY)


# --- privacy ------------------------------------------------------------------


def test_the_prompt_contains_headings_and_no_row_data():
    """The one rule that matters most: no family data ever leaves here."""
    prompt = build_prompt(["W/o Name", "Cas Dt"], FIELDS, [])

    assert "W/o Name" in prompt
    assert "Cas Dt" in prompt

    # Values that might appear in a sheet must never be in the prompt.
    for secret in (
        "9876543210", "Omana Pillai", "SBIN0001234", "4373680Y", "Palakkad",
    ):
        assert secret not in prompt


def test_the_prompt_lists_only_fields_we_actually_have():
    prompt = build_prompt(["Something"], FIELDS, [("panchayat", "Panchayat")])
    assert "widow_name" in prompt
    assert "extra:panchayat" in prompt


# --- the fake -----------------------------------------------------------------


def test_the_fake_understands_army_shorthand():
    engine = MockLLM()
    results = {
        s.heading: s
        for s in engine.suggest_headings(
            ["W/o Name", "Cas Dt", "Svc No", "Distt"], FIELDS, []
        )
    }
    assert results["W/o Name"].target_key == "widow_name"
    assert results["Cas Dt"].target_key == "date_of_death"
    assert results["Svc No"].target_key == "service_number"


def test_the_fake_proposes_a_new_field_when_nothing_fits():
    [suggestion] = MockLLM().suggest_headings(["Ward Member Name"], FIELDS, [])
    assert suggestion.target_key is None
    assert suggestion.new_field_label == "Ward member name"


def test_the_fake_reuses_an_extra_field_added_before():
    [suggestion] = MockLLM().suggest_headings(
        ["Panchayat"], FIELDS, [("panchayat", "Panchayat")]
    )
    assert suggestion.target_key == "extra:panchayat"
    assert suggestion.new_field_label is None


def test_the_fake_is_repeatable():
    engine = MockLLM()
    headings = ["W/o Name", "Zone Code", "S No"]
    first = [(s.heading, s.target_key) for s in engine.suggest_headings(headings, FIELDS, [])]
    second = [(s.heading, s.target_key) for s in engine.suggest_headings(headings, FIELDS, [])]
    assert first == second


def test_row_counters_are_ignored():
    [suggestion] = MockLLM().suggest_headings(["Sr No"], FIELDS, [])
    assert suggestion.target_key == IGNORE


# --- reading the model's reply ------------------------------------------------


def test_json_wrapped_in_a_code_fence_is_still_read():
    text = """```json
    {"columns": [{"heading": "W/o Name", "target_key": "widow_name",
                  "new_field_label": null, "confidence": 90, "reason": "wife of"}]}
    ```"""
    [suggestion] = parse_response(text, ["W/o Name"])
    assert suggestion.target_key == "widow_name"
    assert suggestion.confidence == 90


def test_nonsense_is_ignored_rather_than_crashing():
    assert parse_response("I'm sorry, I can't help with that.", ["X"]) == []
    assert parse_response("", ["X"]) == []


def test_headings_we_did_not_ask_about_are_dropped():
    text = '{"columns": [{"heading": "Invented", "target_key": "widow_name"}]}'
    assert parse_response(text, ["Mob No"]) == []


def test_a_heading_answered_twice_is_only_taken_once():
    text = """{"columns": [
      {"heading": "Mob No", "target_key": "phone", "confidence": 90},
      {"heading": "Mob No", "target_key": "district", "confidence": 10}]}"""
    results = parse_response(text, ["Mob No"])
    assert len(results) == 1
    assert results[0].target_key == "phone"


def test_a_silly_confidence_is_brought_into_range():
    text = '{"columns": [{"heading": "Mob No", "target_key": "phone", "confidence": 900}]}'
    assert parse_response(text, ["Mob No"])[0].confidence == 100


# --- how suggestions are applied ----------------------------------------------


def make_guess(heading: str, target: str | None) -> ColumnGuess:
    return ColumnGuess(heading, 0, target, 95 if target else 0, "", [])


def test_the_llm_cannot_overrule_what_the_rules_already_decided():
    guesses = [make_guess("Mob No", "phone")]
    apply_llm_suggestions(
        guesses,
        [HeadingSuggestion("Mob No", "district", None, 99, "wrong")],
        VALID,
    )
    assert guesses[0].target_key == "phone"


def test_the_llm_cannot_invent_a_field_we_do_not_have():
    guesses = [make_guess("Odd Column", None)]
    apply_llm_suggestions(
        guesses,
        [HeadingSuggestion("Odd Column", "made_up_field", None, 99, "")],
        VALID,
    )
    assert guesses[0].target_key is None


def test_the_llm_cannot_claim_a_field_another_column_already_uses():
    guesses = [make_guess("Mob No", "phone"), make_guess("Cell", None)]
    apply_llm_suggestions(
        guesses, [HeadingSuggestion("Cell", "phone", None, 90, "")], VALID
    )
    assert guesses[1].target_key is None, "two columns were pointed at one field"


def test_a_proposed_new_field_is_only_a_proposal():
    """Nothing is created here — the colonel confirms first."""
    guesses = [make_guess("Ward Member Name", None)]
    apply_llm_suggestions(
        guesses,
        [HeadingSuggestion("Ward Member Name", None, "Ward member name", 70, "new")],
        VALID,
    )
    assert guesses[0].target_key is None
    assert guesses[0].suggested_new_field == "Ward member name"


def test_the_rules_still_run_first():
    """Ordinary headings never need the LLM at all."""
    headers = ["Name of Widow", "Mob No", "Distt"]
    guesses = guess_mapping(headers, [[], [], []])
    assert all(g.target_key is not None for g in guesses)


# --- configuration ------------------------------------------------------------


def test_gemini_refuses_to_start_without_a_key():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        GeminiLLM("", "gemini-2.5-flash", 20.0)
