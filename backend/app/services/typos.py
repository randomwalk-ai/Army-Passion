"""Is a changed value a real update, or probably a typo?

When a row from his sheet matches a family we already have, each value that
differs is either a real change (a new phone number) or most likely a slip of
the keyboard (one digit different). We never decide for him: a typo is only
flagged, so he looks at it before choosing which value to keep.

Field names are the ones a FieldChange uses: "primary_phone",
"soldier.service_number", "child.1.date_of_birth", "extra.door_no".
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

PHONES = {"primary_phone", "alternate_phone", "co_unit_phone"}
CODES = {
    "soldier.service_number",
    "bank_account_number",
    "bank_ifsc",
    "pincode",
    "correspondence_pincode",
    "ppo_number",
}
# Choices and amounts: any difference is a real change, never a typo.
NEVER = {"nok_relationship", "annual_income", "monthly_pension_amount", "gps_coordinates"}
DATE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")


def edit_distance(a: str, b: str) -> int:
    """How many single letters must be added, removed or changed to turn a into b."""
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def _is_date(field_name: str) -> bool:
    return field_name.endswith(("date_of_death", "date_of_birth", "date_of_enrolment"))


def typo_reason(field_name: str, old: str | None, new: str | None) -> str | None:
    """Why this change looks like a typo, in plain words; None if it looks real."""
    if not old or not new or field_name in NEVER:
        return None
    if field_name.startswith("child.") and (
        field_name.count(".") == 1 or field_name.endswith((".gender", ".marital_status"))
    ):
        return None  # a new child, or a choice like sex

    if field_name in PHONES:
        a, b = re.sub(r"\D", "", old)[-10:], re.sub(r"\D", "", new)[-10:]
        if len(a) == len(b) == 10:
            digits = sum(1 for x, y in zip(a, b) if x != y)
            if 1 <= digits <= 2:
                return f"Only {digits} digit{'s' if digits > 1 else ''} different"
        if a and b and edit_distance(a, b) == 1:
            return "One digit added or missing"
        return None

    if _is_date(field_name):
        a, b = DATE.match(old), DATE.match(new)
        if not a or not b:
            return None
        if (a[1], a[2], a[3]) == (b[2], b[1], b[3]):
            return "Day and month swapped"
        if sum(1 for x, y in zip(old, new) if x != y) == 1:
            return "One digit different"
        return None

    if field_name in CODES:
        a = re.sub(r"[^0-9A-Z]", "", old.upper())
        b = re.sub(r"[^0-9A-Z]", "", new.upper())
        if a and b and a != b and edit_distance(a, b) == 1 and min(len(a), len(b)) >= 4:
            return "One character different"
        return None

    # Names and other text: spelt slightly differently.
    a, b = " ".join(old.lower().split()), " ".join(new.lower().split())
    if a == b or min(len(a), len(b)) < 4 or re.fullmatch(r"[\d\s.,]+", a + b):
        return None
    if edit_distance(a, b) <= 2 or SequenceMatcher(None, a, b).ratio() >= 0.85:
        return "Spelt slightly differently"
    return None
