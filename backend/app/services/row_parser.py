"""Turn one row of his sheet into clean values we can store.

Office sheets are typed by people, so the same column holds "14-03-2021",
"14/3/21" and "14 Mar 2021". This normalises all of it, and records a problem
whenever something cannot be read rather than quietly dropping it.

Indian conventions throughout: dates are day-first, phones are +91.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.models.custom_field import EXTRA_PREFIX
from app.models.enums import DeathCauseCategory, IssueCode, IssueSeverity

TODAY = date.today
MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


@dataclass
class FieldProblem:
    field_name: str
    code: IssueCode
    severity: IssueSeverity
    message: str
    raw_value: str = ""


@dataclass
class ParsedRow:
    row_number: int  # as it appears in his sheet, for pointing him at it
    values: dict[str, object] = field(default_factory=dict)
    # Values for approved extra fields, keyed by the field's key.
    extra_fields: dict[str, str] = field(default_factory=dict)
    problems: list[FieldProblem] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)
    # Fields the colonel typed over on the preview. These came from him, not
    # from the file, and the history must say so.
    edited_fields: set[str] = field(default_factory=set)
    # He asked for this row to be left out of the import.
    skipped_by_user: bool = False

    @property
    def has_blocking_problem(self) -> bool:
        """A row with no names at all cannot become a family."""
        return not self.values.get("widow_name") and not self.values.get("soldier_name")

    def get(self, key: str) -> object | None:
        return self.values.get(key)


# --- individual value cleaners ------------------------------------------------


def parse_phone(raw: str) -> tuple[str | None, str | None]:
    """Returns (clean number, reason it failed)."""
    if not raw or not raw.strip():
        return None, None  # blank is not an error here; it is reported separately

    digits = re.sub(r"[^\d]", "", raw)
    # Strip the country code or a leading zero.
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10:
        return None, f"'{raw}' is not a 10-digit number"
    if digits[0] not in "6789":
        return None, f"'{raw}' does not start with 6, 7, 8 or 9"
    return f"+91{digits}", None


def parse_date(raw: str) -> tuple[date | None, str | None]:
    """Day-first, because that is how Indian sheets are written."""
    if not raw or not raw.strip():
        return None, None
    text = raw.strip()

    # "2021-03-14 00:00:00" — Excel sometimes hands back a full timestamp.
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), None
        except ValueError:
            return None, f"'{raw}' is not a real date"

    # "14 Mar 2021"
    worded = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{2,4})$", text)
    if worded:
        month = MONTH_NAMES.get(worded.group(2).lower())
        if month is None:
            return None, f"'{raw}' has a month name I do not recognise"
        return _build_date(worded.group(1), month, worded.group(3), raw)

    # "14-03-2021", "14/3/21", "14.3.21"
    parts = re.split(r"[-/.]", text)
    if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
        return _build_date(parts[0], int(parts[1]), parts[2], raw)

    return None, f"'{raw}' is not a date I can read"


def _build_date(day_s: str, month: int, year_s: str, raw: str):
    try:
        day = int(day_s)
        year = int(year_s)
    except ValueError:
        return None, f"'{raw}' is not a date I can read"

    if year < 100:
        # "21" means 2021, "95" means 1995.
        year += 2000 if year <= (TODAY().year % 100) else 1900

    if not 1 <= month <= 12:
        return None, f"'{raw}' has month {month}"
    try:
        value = date(year, month, day)
    except ValueError:
        return None, f"'{raw}' is not a real date"

    if value > TODAY():
        return None, f"'{raw}' is in the future"
    if value.year < 1940:
        return None, f"'{raw}' looks too long ago"
    return value, None


def parse_amount(raw: str) -> tuple[int | None, str | None]:
    """'₹1,20,000', 'Rs. 95000' or '120000.00' -> an integer number of rupees."""
    if not raw or not raw.strip():
        return None, None

    # Drop currency words and separators, then take the number itself. Matching
    # the number explicitly avoids the full stop in "Rs." being read as a
    # decimal point, which turned 95000 into 1.
    stripped = re.sub(r"[,\s₹]", "", raw)
    match = re.search(r"\d+(?:\.\d+)?", stripped)
    if not match:
        return None, f"'{raw}' is not an amount"
    try:
        return int(round(float(match.group()))), None
    except ValueError:
        return None, f"'{raw}' is not an amount"


def parse_count(raw: str) -> tuple[int | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    cleaned = raw.strip()
    if cleaned.lower() in {"nil", "none", "-"}:
        return 0, None
    if not cleaned.isdigit():
        return None, f"'{raw}' is not a number"
    return int(cleaned), None


def parse_pincode(raw: str) -> tuple[str | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) != 6 or digits[0] == "0":
        return None, f"'{raw}' is not a 6-digit PIN code"
    return digits, None


def parse_ifsc(raw: str) -> tuple[str | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    cleaned = raw.strip().upper().replace(" ", "")
    if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", cleaned):
        return None, f"'{raw}' is not a valid IFSC code"
    return cleaned, None


def parse_geolocation(raw: str) -> tuple[str | None, str | None]:
    """'28.6139, 77.2090' (or space-separated) -> '28.613900, 77.209000'."""
    if not raw or not raw.strip():
        return None, None
    numbers = re.findall(r"-?\d+(?:\.\d+)?", raw)
    if len(numbers) != 2:
        return None, f"'{raw}' is not a latitude and longitude"
    lat, lon = float(numbers[0]), float(numbers[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, f"'{raw}' is outside the range of a real location"
    return f"{lat:.6f}, {lon:.6f}", None


def parse_email(raw: str) -> tuple[str | None, str | None]:
    if not raw or not raw.strip():
        return None, None
    cleaned = raw.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
        return None, f"'{raw}' is not an email address"
    return cleaned, None


def parse_sex(raw: str) -> tuple[str | None, str | None]:
    """The colonel's sheet uses M/F."""
    if not raw or not raw.strip():
        return None, None
    value = raw.strip().lower()
    if value in {"m", "male", "boy", "son"}:
        return "male", None
    if value in {"f", "female", "girl", "daughter"}:
        return "female", None
    return None, f"'{raw}' is not M or F"


# Titles the colonel's sheet puts in front of names ("SMT VEDVATE",
# "LATE RAJVIR SINGH"). Left in, they stop the same person being recognised.
# "Kumari" is deliberately absent: it is also a common first name.
NAME_TITLES = {"smt", "shrimati", "shri", "sh", "late", "mrs", "mr", "ms", "km", "kum"}


def tidy_name(raw: str) -> str | None:
    """'SMT  SUNITA DEVI ' -> 'Sunita Devi'. Sheets often shout in capitals."""
    if not raw or not raw.strip():
        return None
    collapsed = re.sub(r"\s+", " ", raw.strip())
    words = collapsed.split(" ")
    while len(words) > 1 and words[0].lower().rstrip(".") in NAME_TITLES:
        words = words[1:]
    collapsed = " ".join(words)
    if collapsed.isupper() or collapsed.islower():
        collapsed = collapsed.title()
    return collapsed


# Free-text causes from the sheet, grouped into our categories.
CAUSE_KEYWORDS: list[tuple[DeathCauseCategory, tuple[str, ...]]] = [
    (DeathCauseCategory.battle_casualty,
     ("killed in action", "enemy", "ied", "firing", "ambush", "operation", "militant",
      "battle", "terrorist")),
    (DeathCauseCategory.accident,
     ("accident", "road", "vehicle", "fall", "drown", "electro", "crash")),
    (DeathCauseCategory.physical_casualty,
     ("avalanche", "altitude", "frostbite", "landslide", "heat stroke", "exposure")),
    (DeathCauseCategory.illness,
     ("illness", "cancer", "heart", "cardiac", "kidney", "tb", "tuberculosis",
      "stroke", "disease", "sick", "liver")),
    (DeathCauseCategory.suicide, ("suicide", "self inflicted", "self-inflicted")),
    (DeathCauseCategory.natural_causes, ("natural", "old age", "age related")),
]


def parse_cause(raw: str) -> tuple[DeathCauseCategory | None, str | None]:
    """Returns (category, the original text kept as the sub-cause)."""
    if not raw or not raw.strip():
        return None, None
    text = raw.strip().lower()
    for category, keywords in CAUSE_KEYWORDS:
        if any(word in text for word in keywords):
            return category, raw.strip()
    return DeathCauseCategory.other, raw.strip()


# --- the whole row ------------------------------------------------------------

# field key -> (cleaner, issue code used when it fails)
CLEANERS = {
    "phone": (parse_phone, IssueCode.invalid_phone),
    "alternate_phone": (parse_phone, IssueCode.invalid_phone),
    "date_of_death": (parse_date, IssueCode.invalid_date),
    "annual_income": (parse_amount, IssueCode.outdated_information),
    "monthly_pension_amount": (parse_amount, IssueCode.outdated_information),
    "children_count": (parse_count, IssueCode.outdated_information),
    "pincode": (parse_pincode, IssueCode.missing_address),
    "bank_ifsc": (parse_ifsc, IssueCode.missing_bank_details),
    "geolocation": (parse_geolocation, IssueCode.missing_address),
    "email": (parse_email, IssueCode.outdated_information),
    "co_unit_phone": (parse_phone, IssueCode.invalid_phone),
    "correspondence_pincode": (parse_pincode, IssueCode.missing_address),
}
for _n in (1, 2, 3):
    CLEANERS[f"child{_n}_dob"] = (parse_date, IssueCode.invalid_date)
    CLEANERS[f"child{_n}_sex"] = (parse_sex, IssueCode.outdated_information)

NAME_FIELDS = {
    "widow_name", "soldier_name", "child1_name", "child2_name", "child3_name",
}
PLAIN_TEXT_FIELDS = {
    "rank", "unit", "regiment", "service_number", "place_of_death",
    "village_or_town", "town", "tehsil", "post_office", "district", "state",
    "nok_relationship", "ppo_number", "bank_account_number", "bank_name",
    "bank_branch", "bank_account_holder", "bank_address", "co_unit_name",
    "record_office", "correspondence_address", "notes",
    "child1_marital_status", "child2_marital_status", "child3_marital_status",
}


def parse_row(
    row: list[str],
    mapping: dict[str, str],
    headers: list[str],
    row_number: int,
) -> ParsedRow:
    """`mapping` is {heading: field key}, as he confirmed it."""
    parsed = ParsedRow(row_number=row_number)

    for index, heading in enumerate(headers):
        target = mapping.get(heading)
        if not target or target == "__ignore__":
            continue
        raw = row[index].strip() if index < len(row) else ""
        parsed.raw[target] = raw

        # An extra field: kept as plain text in the family's pocket. We do not
        # know what it means, so we do not try to clean it up.
        if target.startswith(EXTRA_PREFIX):
            key = target[len(EXTRA_PREFIX) :]
            if raw:
                parsed.extra_fields[key] = re.sub(r"\s+", " ", raw)
            continue

        if target in NAME_FIELDS:
            parsed.values[target] = tidy_name(raw)
            continue

        if target == "cause_of_death":
            category, text = parse_cause(raw)
            if category:
                parsed.values["cause_category"] = category
                parsed.values["cause_sub_category"] = text
            continue

        if target in CLEANERS:
            cleaner, code = CLEANERS[target]
            value, problem = cleaner(raw)
            if problem:
                parsed.problems.append(
                    FieldProblem(
                        field_name=target,
                        code=code,
                        severity=IssueSeverity.high
                        if target in {"phone", "date_of_death"}
                        else IssueSeverity.medium,
                        message=problem,
                        raw_value=raw,
                    )
                )
            elif value is not None:
                parsed.values[target] = value
            continue

        if target in PLAIN_TEXT_FIELDS and raw:
            parsed.values[target] = re.sub(r"\s+", " ", raw)

    _flag_missing(parsed)
    return parsed


def _flag_missing(parsed: ParsedRow) -> None:
    """Things that are absent rather than wrong."""
    if not parsed.raw.get("phone", "").strip():
        parsed.problems.append(
            FieldProblem(
                "phone",
                IssueCode.missing_phone,
                IssueSeverity.high,
                "No phone number in this row",
            )
        )
    if "date_of_death" in parsed.raw and not parsed.values.get("date_of_death"):
        if not parsed.raw["date_of_death"].strip():
            parsed.problems.append(
                FieldProblem(
                    "date_of_death",
                    IssueCode.missing_date_of_death,
                    IssueSeverity.high,
                    "No date of death in this row",
                )
            )


def apply_overrides(parsed: ParsedRow, override: dict | None) -> ParsedRow:
    """Replace values with the colonel's corrections, checking them the same way.

    A value he types goes through exactly the same cleaning and validation as
    one from the file, so he cannot type a phone number the import would
    later reject.
    """
    if not override:
        return parsed

    if override.get("skip"):
        parsed.skipped_by_user = True

    for target, raw_value in (override.get("values") or {}).items():
        raw = str(raw_value).strip()
        parsed.raw[target] = raw
        parsed.edited_fields.add(target)
        # Drop any problem the file's version of this field had.
        parsed.problems = [p for p in parsed.problems if p.field_name != target]

        if target.startswith(EXTRA_PREFIX):
            key = target[len(EXTRA_PREFIX) :]
            if raw:
                parsed.extra_fields[key] = re.sub(r"\s+", " ", raw)
            else:
                parsed.extra_fields.pop(key, None)
            continue

        if not raw:
            parsed.values.pop(target, None)
            if target == "cause_of_death":
                parsed.values.pop("cause_category", None)
                parsed.values.pop("cause_sub_category", None)
            continue

        if target in NAME_FIELDS:
            parsed.values[target] = tidy_name(raw)
        elif target == "cause_of_death":
            category, text = parse_cause(raw)
            parsed.values["cause_category"] = category
            parsed.values["cause_sub_category"] = text
        elif target in CLEANERS:
            cleaner, code = CLEANERS[target]
            value, problem = cleaner(raw)
            if problem:
                parsed.values.pop(target, None)
                parsed.problems.append(
                    FieldProblem(
                        field_name=target,
                        code=code,
                        severity=IssueSeverity.high,
                        message=f"You typed {problem}",
                        raw_value=raw,
                    )
                )
            else:
                parsed.values[target] = value
        else:
            parsed.values[target] = re.sub(r"\s+", " ", raw)

    return parsed
