"""Guess what each column in an uploaded sheet means.

We do not have the colonel's real sheet yet, so nothing is hard-coded to one
file. The system guesses from the heading text and the values underneath, then
shows its guess for him to correct. His corrections are saved and reused, so
the second upload of the same sheet needs no work.

The guessing is deliberately plain rules, not AI: it must give the same answer
every time, and he must be able to understand why it guessed what it did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- the fields a sheet can map onto -----------------------------------------


@dataclass(frozen=True)
class TargetField:
    key: str
    label: str
    group: str
    required: bool = False


TARGET_FIELDS: list[TargetField] = [
    # --- the soldier ---
    TargetField("soldier_name", "Soldier's name", "Soldier", required=True),
    TargetField("rank", "Rank", "Soldier"),
    TargetField("service_number", "Army number", "Soldier"),
    TargetField("unit", "Serving unit", "Soldier"),
    TargetField("regiment", "Parent unit", "Soldier"),
    TargetField("date_of_death", "Date of casualty", "Soldier"),
    TargetField("cause_of_death", "Cause of death", "Soldier"),
    TargetField("place_of_death", "Place of death", "Soldier"),
    # --- next of kin ---
    TargetField("widow_name", "Name of NOK", "Next of kin", required=True),
    TargetField("nok_relationship", "Relationship", "Next of kin"),
    TargetField("phone", "Phone number", "Next of kin"),
    TargetField("alternate_phone", "NOK telephone", "Next of kin"),
    TargetField("email", "Email", "Next of kin"),
    # --- address ---
    TargetField("village_or_town", "Village", "Address"),
    TargetField("town", "Town", "Address"),
    TargetField("tehsil", "Tehsil", "Address"),
    TargetField("post_office", "Post office", "Address"),
    TargetField("district", "District", "Address"),
    TargetField("state", "State", "Address"),
    TargetField("pincode", "PIN code", "Address"),
    TargetField("geolocation", "GPS location of house", "Address"),
    # --- children (up to three, as the colonel's sheet lays them out) ---
    TargetField("child1_name", "Child 1 name", "Children"),
    TargetField("child1_sex", "Child 1 sex", "Children"),
    TargetField("child1_dob", "Child 1 date of birth", "Children"),
    TargetField("child1_marital_status", "Child 1 marital status", "Children"),
    TargetField("child2_name", "Child 2 name", "Children"),
    TargetField("child2_sex", "Child 2 sex", "Children"),
    TargetField("child2_dob", "Child 2 date of birth", "Children"),
    TargetField("child2_marital_status", "Child 2 marital status", "Children"),
    TargetField("child3_name", "Child 3 name", "Children"),
    TargetField("child3_sex", "Child 3 sex", "Children"),
    TargetField("child3_dob", "Child 3 date of birth", "Children"),
    TargetField("child3_marital_status", "Child 3 marital status", "Children"),
    # --- pension and bank ---
    TargetField("ppo_number", "PPO number", "Pension and bank"),
    TargetField("bank_name", "Pension bank", "Pension and bank"),
    TargetField("bank_branch", "Pension bank branch", "Pension and bank"),
    TargetField("bank_account_number", "Bank account number", "Pension and bank"),
    TargetField("bank_ifsc", "IFSC code", "Pension and bank"),
    TargetField("bank_account_holder", "Account holder's name", "Pension and bank"),
    TargetField("bank_address", "Bank address", "Pension and bank"),
    # --- unit contact ---
    TargetField("co_unit_name", "CO unit name", "Unit contact"),
    TargetField("co_unit_phone", "CO unit telephone", "Unit contact"),
    # --- needed by the CEA form ---
    TargetField("record_office", "Record office", "CEA"),
    TargetField("correspondence_address", "Correspondence address", "CEA"),
    TargetField("correspondence_pincode", "Correspondence PIN code", "CEA"),
    # --- other ---
    TargetField("children_count", "Number of children", "Other"),
    TargetField("annual_income", "Annual income", "Other"),
    TargetField("monthly_pension_amount", "Monthly pension", "Other"),
    TargetField("notes", "Notes or remarks", "Other"),
]

# The child fields, by child number, for code that needs to walk them.
CHILD_SLOTS = (1, 2, 3)
CHILD_PARTS = ("name", "sex", "dob", "marital_status")

TARGET_BY_KEY = {f.key: f for f in TARGET_FIELDS}

# A column can also be deliberately skipped.
IGNORE = "__ignore__"


# --- heading synonyms ---------------------------------------------------------
# Written the way office sheets actually write them, abbreviations included.

SYNONYMS: dict[str, list[str]] = {
    "widow_name": [
        "name of widow", "widow name", "widow", "nok name", "next of kin",
        "name of nok", "wife name", "name of wife", "beneficiary name",
        "claimant name", "spouse name", "widow s name",
    ],
    "soldier_name": [
        "husband name", "name of husband", "name of deceased", "deceased name",
        "soldier name", "name of soldier", "martyr name", "name of individual",
        "ex serviceman name", "esm name", "late", "name of late",
        # The colonel's sheet just says "NAME" for the soldier.
        "name", "sainik name", "name of sainik",
    ],
    "rank": ["rank", "last rank", "rank held", "designation"],
    "service_number": [
        "army no", "army number", "service no", "service number", "regt no",
        "personal no", "ic no", "no", "army nos", "sainik army no",
        "sainik army number",
    ],
    "unit": [
        "unit", "regt", "regiment", "regt unit", "corps", "regt or unit",
        "unit regt", "arm", "arm service", "serving unit", "last unit served",
        "last unit",
    ],
    "regiment": ["parent unit", "parent regt", "parent regiment", "parent corps"],
    "date_of_death": [
        "date of casualty", "date of death", "dod", "doc", "casualty date",
        "date of demise", "death date", "expired on", "date of expiry",
        # As spelled in the colonel's field list.
        "date of caualty",
    ],
    "nok_relationship": [
        "relationship", "relation", "relationship of nok", "relation with deceased",
        "relationship with deceased", "nok relationship",
    ],
    "email": ["email", "e mail", "email id", "mail id"],
    "town": ["town", "city"],
    "tehsil": ["tehsil", "taluk", "taluka", "mandal", "tahsil"],
    "post_office": ["post office", "po", "p o"],
    "geolocation": [
        "geolocation", "geo location", "gps", "gps location", "nok gpspin",
        "gps pin", "lat long", "latitude longitude", "coordinates",
    ],
    "ppo_number": ["ppo", "ppo no", "ppo number", "pension payment order"],
    "bank_branch": ["pension bank branch", "bank branch", "branch name"],
    "bank_account_holder": ["account holder", "account holder name", "a c holder"],
    "bank_address": ["bank address", "address of bank"],
    "co_unit_name": ["co unit name", "co unit", "unit co name"],
    "co_unit_phone": [
        "co unit telephone no1", "co unit telephone no", "co unit telephone",
        "co unit phone", "unit telephone",
    ],
    "record_office": ["record office", "name of records", "records office"],
    "correspondence_address": ["correspondence address", "address for correspondence"],
    "correspondence_pincode": ["correspondence pin", "correspondence pin code"],
    "cause_of_death": [
        "cause", "cause of death", "cause of casualty", "casualty type",
        "nature of death", "reason",
    ],
    "place_of_death": ["place of death", "place of casualty", "location of death"],
    "phone": [
        "mob no", "mobile", "mobile no", "mobile number", "phone", "phone no",
        "contact no", "contact number", "cell no", "tel", "telephone",
        "mob", "contact", "tele no", "tel no", "telephone no",
    ],
    "alternate_phone": [
        "alt mobile", "alternate no", "alternate mobile", "second mobile",
        "other contact", "mob no 2", "nok telephone", "nok phone", "nok mobile",
        "contact number of nok",
    ],
    "village_or_town": [
        "village", "village town", "vill", "address", "postal address",
        "residence", "village post",
    ],
    "district": ["distt", "district", "dist", "zila", "zilla"],
    "state": ["state", "province"],
    "pincode": ["pin", "pin code", "pincode", "postal code", "zip"],
    "bank_account_number": [
        "bank a c no", "account no", "a c no", "bank account", "acct no",
        "account number", "saving a c", "bank account number",
    ],
    "bank_ifsc": ["ifsc", "ifsc code", "ifs code", "branch code"],
    "bank_name": ["bank", "bank name", "name of bank", "pension bank"],
    "children_count": [
        "no of children", "number of children", "children", "no of kids",
        "dependents", "no of dependents",
    ],
    "annual_income": [
        "annual income", "income", "yearly income", "annual income rs",
        "family income",
    ],
    "monthly_pension_amount": [
        "pension", "monthly pension", "pension amount", "family pension",
    ],
    "notes": ["remarks", "remark", "notes", "comments", "observation"],
}

# The colonel's sheet lays children out side by side: Name_of_Child1,
# Sex_Child1, DOB_Child1, Marital_Status_Child1, then the same for 2 and 3.
for _n in CHILD_SLOTS:
    SYNONYMS[f"child{_n}_name"] = [
        f"name of child{_n}", f"name of child {_n}", f"child{_n} name",
        f"child {_n} name", f"child{_n}",
    ]
    SYNONYMS[f"child{_n}_sex"] = [
        f"sex child{_n}", f"sex child {_n}", f"child{_n} sex", f"gender child{_n}",
    ]
    SYNONYMS[f"child{_n}_dob"] = [
        f"dob child{_n}", f"dob child {_n}", f"child{_n} dob",
        f"date of birth child{_n}",
    ]
    SYNONYMS[f"child{_n}_marital_status"] = [
        f"marital status child{_n}", f"marital status child {_n}",
        f"child{_n} marital status",
    ]

# Synonyms so short and common that they may only match a heading exactly.
# "NAME" is how the colonel's sheet heads the soldier's name; without this,
# every heading containing the word "name" would be read as the soldier's.
EXACT_ONLY = {"name"}

# Headings that are clearly not data we want.
IGNORE_HEADINGS = [
    "s no", "sr no", "serial", "sl no", "si no", "#", "index", "row no", "sno",
]

# Document columns hold files, which are attached to a family or child
# separately rather than read out of a spreadsheet cell.
DOCUMENT_HEADING_RE = re.compile(r"^documents?( \d+)?$")


def normalise(heading: str) -> str:
    """'Bank A/c No.' -> 'bank a c no' so spellings stop mattering."""
    lowered = heading.lower().strip()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", collapsed).strip()


# --- looking at the values, not just the heading ------------------------------

PHONE_RE = re.compile(r"^(\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.IGNORECASE)
PINCODE_RE = re.compile(r"^[1-9]\d{5}$")
DATE_RE = re.compile(
    r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}$|^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}$"
)
SERVICE_NO_RE = re.compile(r"^(IC[-\s]?)?\d{5,9}[A-Z]?$", re.IGNORECASE)


def guess_from_values(samples: list[str]) -> tuple[str | None, int]:
    """Look at the actual values. Returns (field key, confidence 0-100)."""
    if not samples:
        return None, 0

    cleaned = [s.strip() for s in samples if s.strip()]
    if not cleaned:
        return None, 0

    def share(test) -> float:
        return sum(1 for s in cleaned if test(s)) / len(cleaned)

    checks: list[tuple[str, float]] = [
        ("phone", share(lambda s: bool(PHONE_RE.match(s.replace(" ", ""))))),
        ("bank_ifsc", share(lambda s: bool(IFSC_RE.match(s)))),
        ("pincode", share(lambda s: bool(PINCODE_RE.match(s)))),
        ("date_of_death", share(lambda s: bool(DATE_RE.match(s)))),
        ("service_number", share(lambda s: bool(SERVICE_NO_RE.match(s)))),
    ]
    best_key, best_share = max(checks, key=lambda c: c[1])
    if best_share >= 0.6:
        return best_key, int(best_share * 100)
    return None, 0


# --- the result ---------------------------------------------------------------


@dataclass
class ColumnGuess:
    source_heading: str
    column_index: int
    target_key: str | None  # a field key, IGNORE, or None for "not sure"
    confidence: int  # 0-100
    reason: str
    samples: list[str]
    # Set when nothing fits and we propose storing it as a new field.
    # The field is only created once the colonel confirms.
    suggested_new_field: str | None = None


def guess_column(heading: str, samples: list[str], index: int) -> ColumnGuess:
    normalised = normalise(heading)

    if normalised in IGNORE_HEADINGS:
        return ColumnGuess(heading, index, IGNORE, 95, "Looks like a row number", samples)

    if DOCUMENT_HEADING_RE.match(normalised):
        return ColumnGuess(
            heading, index, IGNORE, 95,
            "Documents are attached to the family separately, not read from the sheet",
            samples,
        )

    # 1. Exact heading match — the strongest signal.
    for key, options in SYNONYMS.items():
        if normalised in options:
            return ColumnGuess(
                heading, index, key, 95, f"Heading matches '{heading}'", samples
            )

    # 2. Heading contains a known phrase.
    for key, options in SYNONYMS.items():
        for option in options:
            if option in EXACT_ONLY:
                continue
            if len(option) >= 4 and option in normalised:
                return ColumnGuess(
                    heading, index, key, 75, f"Heading contains '{option}'", samples
                )

    # 3. Fall back to what the values look like.
    value_key, value_confidence = guess_from_values(samples)
    if value_key:
        return ColumnGuess(
            heading,
            index,
            value_key,
            min(value_confidence, 70),
            "Guessed from the values in this column",
            samples,
        )

    return ColumnGuess(heading, index, None, 0, "Could not work this one out", samples)


def guess_mapping(
    headers: list[str],
    samples_for: list[list[str]],
    known_extras: dict[str, str] | None = None,
) -> list[ColumnGuess]:
    """Guess every column, then make sure no field is claimed twice.

    `known_extras` maps an extra field's key to its label, e.g.
    {"ward_member_name": "Ward member name"}. A heading that matches one of
    those is pointed at the existing extra field rather than becoming a
    second, nearly identical one.
    """
    guesses = [
        guess_column(heading, samples_for[i], i) for i, heading in enumerate(headers)
    ]

    # Before anything else, reuse extra fields that were approved earlier.
    if known_extras:
        by_normalised = {normalise(label): key for key, label in known_extras.items()}
        for guess in guesses:
            if guess.target_key is not None:
                continue
            match = by_normalised.get(normalise(guess.source_heading))
            if match:
                guess.target_key = f"extra:{match}"
                guess.confidence = 90
                guess.reason = "You added this extra field before"

    # If two columns claim the same field, the more confident one keeps it.
    claimed: dict[str, ColumnGuess] = {}
    for guess in guesses:
        key = guess.target_key
        if key is None or key == IGNORE:
            continue
        held = claimed.get(key)
        if held is None:
            claimed[key] = guess
        elif guess.confidence > held.confidence:
            held.target_key = None
            held.confidence = 0
            held.reason = f"'{guess.source_heading}' is a better match for this field"
            claimed[key] = guess
        else:
            guess.target_key = None
            guess.confidence = 0
            guess.reason = f"'{held.source_heading}' is a better match for this field"

    return guesses


def apply_llm_suggestions(
    guesses: list[ColumnGuess],
    suggestions: list,
    valid_keys: set[str],
) -> None:
    """Fill in the columns the rules could not work out.

    The LLM never overrides a column the rules already matched, and it can
    only choose a field that actually exists. A proposed new field is only a
    proposal — nothing is created until the colonel confirms.
    """
    by_heading = {s.heading: s for s in suggestions}
    claimed = {g.target_key for g in guesses if g.target_key}

    for guess in guesses:
        if guess.target_key is not None:
            continue
        suggestion = by_heading.get(guess.source_heading)
        if suggestion is None:
            continue

        key = suggestion.target_key
        if key and (key in valid_keys or key == IGNORE):
            if key in claimed and key != IGNORE:
                continue  # another column already feeds this field
            guess.target_key = key
            guess.confidence = suggestion.confidence
            guess.reason = suggestion.reason or "Worked out by AI"
            claimed.add(key)
        elif suggestion.new_field_label:
            guess.suggested_new_field = suggestion.new_field_label
            guess.confidence = suggestion.confidence
            guess.reason = suggestion.reason or "Not one of our fields"


def unmapped_required_fields(guesses: list[ColumnGuess]) -> list[TargetField]:
    """Required fields that nothing points at yet."""
    mapped = {g.target_key for g in guesses}
    return [f for f in TARGET_FIELDS if f.required and f.key not in mapped]
