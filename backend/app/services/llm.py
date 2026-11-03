"""The LLM, behind an interface.

Used for one narrow job so far: working out what a column heading means when
our rules do not recognise it.

PRIVACY: only column HEADINGS are ever sent. No names, phone numbers, bank
details or any other row content leaves this machine. The LLM does not need
to see a widow's details to know that "Cas Dt" means date of death.

If the LLM is slow, unreachable or returns nonsense, the upload still works —
the column simply stays unrecognised and the colonel is asked about it.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Never send more than this many headings in one request.
MAX_HEADINGS = 60


@dataclass
class HeadingSuggestion:
    """What the LLM thinks one unrecognised heading means."""

    heading: str
    # One of our field keys, or None when it does not fit any of them.
    target_key: str | None
    # A tidy name to store it under, when it fits none of our fields.
    new_field_label: str | None
    confidence: int  # 0-100
    reason: str


class LLM(ABC):
    @abstractmethod
    def suggest_headings(
        self,
        headings: list[str],
        fields: list[tuple[str, str]],
        existing_extras: list[tuple[str, str]],
    ) -> list[HeadingSuggestion]:
        """`fields` and `existing_extras` are (key, label) pairs."""


def build_prompt(
    headings: list[str],
    fields: list[tuple[str, str]],
    existing_extras: list[tuple[str, str]],
) -> str:
    """The instruction sent to the model. Headings only — never row data."""
    field_lines = "\n".join(f"- {key}: {label}" for key, label in fields)
    extra_lines = (
        "\n".join(f"- extra:{key}: {label}" for key, label in existing_extras)
        or "- (none yet)"
    )
    heading_lines = "\n".join(f"- {h}" for h in headings)

    return f"""You are helping import an Indian Army welfare office spreadsheet
about the families of soldiers who have died.

Each spreadsheet column heading must be matched to one of our database fields.

OUR STANDARD FIELDS (use the key exactly):
{field_lines}

EXTRA FIELDS ADDED EARLIER (reuse these rather than inventing a new one):
{extra_lines}

COLUMN HEADINGS TO IDENTIFY:
{heading_lines}

Notes on this domain:
- "NOK" means next of kin, usually the widow.
- "W/o" means wife of, so that column holds the widow's name.
- "Casualty" in this context means the soldier's death.
- "Distt" means district. "Regt" means regiment. "Army No" is a service number.
- A heading that is only a row counter (S.No, Sr No) should be ignored.

Reply with JSON only, no explanation around it, in exactly this shape:
{{"columns": [
  {{"heading": "<the heading exactly as given>",
    "target_key": "<a field key above, or null>",
    "new_field_label": "<a short tidy name, or null>",
    "confidence": <0-100>,
    "reason": "<a short reason, max 12 words>"}}
]}}

Rules:
- Use target_key when the heading clearly matches one of our fields.
- When it matches none of them, set target_key to null and give a
  new_field_label: a tidy, human-readable name for a new field.
- Use "__ignore__" as target_key for row counters.
- Never invent a field key that is not in the lists above.
- Include every heading exactly once."""


def parse_response(text: str, headings: list[str]) -> list[HeadingSuggestion]:
    """Read the model's JSON, ignoring anything it wrapped around it."""
    cleaned = text.strip()
    # Models often wrap JSON in a ```json fence, or add a line of chat around
    # it. Taking everything between the first { and the last } handles both,
    # and avoids a regex that backtracks badly on long replies.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM did not return readable JSON; ignoring its answer.")
        return []

    wanted = {h.lower(): h for h in headings}
    suggestions: list[HeadingSuggestion] = []
    seen: set[str] = set()

    for row in data.get("columns", []):
        if not isinstance(row, dict):
            continue
        heading = str(row.get("heading", "")).strip()
        original = wanted.get(heading.lower())
        # Ignore anything that is not one of the headings we asked about.
        if original is None or original in seen:
            continue
        seen.add(original)

        target = row.get("target_key")
        target = str(target) if target else None
        label = row.get("new_field_label")
        label = str(label).strip() if label else None

        try:
            confidence = max(0, min(100, int(row.get("confidence", 50))))
        except (TypeError, ValueError):
            confidence = 50

        suggestions.append(
            HeadingSuggestion(
                heading=original,
                target_key=target,
                new_field_label=label,
                confidence=confidence,
                reason=str(row.get("reason", ""))[:120],
            )
        )

    return suggestions


# --- the fake ----------------------------------------------------------------

# Headings the fake understands, so the whole flow can be built and tested
# without an API key, an internet connection, or any cost.
# Keys must already be normalised: lower case, punctuation turned into spaces,
# so "W/o Name" is looked up as "w o name".
MOCK_KNOWN: dict[str, str] = {
    "w o name": "widow_name",
    "wo name": "widow_name",
    "nok": "widow_name",
    "nok name": "widow_name",
    "name of nok": "widow_name",
    "cas dt": "date_of_death",
    "cas date": "date_of_death",
    "dt of cas": "date_of_death",
    "mob": "phone",
    "cell": "phone",
    "contact": "phone",
    "regt": "unit",
    "svc no": "service_number",
    "pers no": "service_number",
    "dist": "district",
    "blk": "village_or_town",
    "block": "village_or_town",
}

MOCK_IGNORE = {"s no", "sr no", "sl no", "si no", "serial", "sno", "#"}


def _tidy_label(heading: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", heading).strip()
    return cleaned[:1].upper() + cleaned[1:].lower() if cleaned else heading


class MockLLM(LLM):
    """Sends nothing anywhere. Same answer every time, so tests are stable."""

    def suggest_headings(
        self,
        headings: list[str],
        fields: list[tuple[str, str]],
        existing_extras: list[tuple[str, str]],
    ) -> list[HeadingSuggestion]:
        valid_keys = {key for key, _ in fields}
        extras_by_label = {
            label.lower(): key for key, label in existing_extras
        }

        suggestions: list[HeadingSuggestion] = []
        for heading in headings[:MAX_HEADINGS]:
            simple = re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()

            if simple in MOCK_IGNORE:
                suggestions.append(
                    HeadingSuggestion(
                        heading, "__ignore__", None, 90, "Looks like a row number"
                    )
                )
                continue

            known = MOCK_KNOWN.get(simple)
            if known and known in valid_keys:
                suggestions.append(
                    HeadingSuggestion(
                        heading, known, None, 85, "Recognised this way of writing it"
                    )
                )
                continue

            reused = extras_by_label.get(simple)
            if reused:
                suggestions.append(
                    HeadingSuggestion(
                        heading, f"extra:{reused}", None, 85, "An extra field you added before"
                    )
                )
                continue

            # Anything else becomes a proposed new field.
            suggestions.append(
                HeadingSuggestion(
                    heading,
                    None,
                    _tidy_label(heading),
                    70,
                    "Not one of our fields - suggest storing as new information",
                )
            )

        return suggestions


# --- Gemini -------------------------------------------------------------------

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Used when LLM_MODEL is left blank in .env.
#
# The "-latest" alias is deliberate: Google retires named versions for new
# accounts, and a retired name fails with a confusing 404. The alias keeps
# working.
#
# flash-lite rather than the larger flash: this job is sorting a handful of
# column headings into 21 known fields. Measured on this prompt, the big
# model took 46 seconds and the lite model 2.4, for identical answers.
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"


class GeminiLLM(LLM):
    """Google's Gemini, over plain HTTP so we need no extra library."""

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise ValueError(
                "LLM_PROVIDER is set to gemini but LLM_API_KEY is empty. "
                "Put your key in .env, or set LLM_PROVIDER=mock."
            )
        self.api_key = api_key
        self.model = (model or "").strip() or DEFAULT_GEMINI_MODEL
        self.timeout = timeout

    def _safe_error(self, exc: Exception) -> str:
        """Never let the API key appear in a log line or an error message."""
        text = str(exc)
        if self.api_key:
            text = text.replace(self.api_key, "***")
        # Belt and braces in case it is url-encoded or partly shown.
        return re.sub(r"(key=)[^&\s'\"]+", r"\1***", text)

    def suggest_headings(
        self,
        headings: list[str],
        fields: list[tuple[str, str]],
        existing_extras: list[tuple[str, str]],
    ) -> list[HeadingSuggestion]:
        prompt = build_prompt(headings[:MAX_HEADINGS], fields, existing_extras)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
            },
        }

        try:
            response = httpx.post(
                GEMINI_URL.format(model=self.model),
                # The key goes in a header, never in the URL. A URL with the
                # key in it ends up in error messages, logs and proxy records.
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001 - never let this break an upload
            logger.warning(
                "Gemini could not be reached (%s); carrying on without it.",
                self._safe_error(exc),
            )
            return []

        return parse_response(text, headings)


# --- reading a voice-note transcript ------------------------------------------
#
# PRIVACY: unlike the column-mapping prompt, this ONE sends real personal
# content — the family's own words about their health, money and situation.
# It must only run once billing is enabled on the Gemini account, so the
# no-training terms apply. Check Google's current terms before pointing this
# at a real recording; mock transcripts are safe to test with at any time.


@dataclass
class FamilyGuess:
    family_id: int
    family_code: str
    confidence: int
    reason: str


@dataclass
class SuggestedFieldChange:
    field_key: str
    label: str
    new_value: str
    reason: str


@dataclass
class TranscriptAnalysis:
    family_guess: FamilyGuess | None
    field_changes: list[SuggestedFieldChange]


# The fields a transcript is allowed to propose changing. Deliberately a
# short, low-risk list — never bank details or anything that moves money.
TRANSCRIPT_EDITABLE_FIELDS = [
    ("phone", "Phone number"),
    ("alternate_phone", "Alternate phone"),
    ("village_or_town", "Village or town"),
    ("district", "District"),
    ("state", "State"),
]


def build_transcript_prompt(
    transcript: str, families: list[tuple[int, str, str, str | None]]
) -> str:
    """`families` is (id, code, widow_name, district) for the candidates to
    choose from — a short list the caller has already narrowed down, never
    the whole database, so the prompt stays small."""
    family_lines = "\n".join(
        f"- id={fid} code={code} name=\"{name}\" district={district or '?'}"
        for fid, code, name, district in families
    )
    field_lines = "\n".join(f"- {key}: {label}" for key, label in TRANSCRIPT_EDITABLE_FIELDS)

    return f"""You are helping an Indian Army welfare office process a phone call
transcript about a soldier's family.

CANDIDATE FAMILIES (pick the one this call is about, or none):
{family_lines}

TRANSCRIPT:
\"\"\"{transcript}\"\"\"

FIELDS THAT CAN BE UPDATED FROM A CALL (use the key exactly):
{field_lines}

Reply with JSON only, in exactly this shape:
{{"family": {{"id": <id from the list above, or null>, "confidence": <0-100>,
             "reason": "<short reason>"}},
  "changes": [
    {{"field_key": "<one of the keys above>", "new_value": "<the new value>",
      "reason": "<short reason, quoting or paraphrasing the transcript>"}}
  ]}}

Rules:
- Only propose a change when the transcript clearly states a new value.
- Never guess a phone number or address that was not actually said.
- If nothing in the transcript suggests a change, return an empty changes list.
- Only choose a family id from the candidates listed above, or null."""


def parse_transcript_response(
    text: str, families: list[tuple[int, str, str, str | None]]
) -> TranscriptAnalysis:
    by_id = {fid: code for fid, code, _, _ in families}
    valid_fields = {key for key, _ in TRANSCRIPT_EDITABLE_FIELDS}

    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM did not return readable JSON for a transcript; ignoring it.")
        return TranscriptAnalysis(family_guess=None, field_changes=[])

    guess = None
    family_data = data.get("family") or {}
    family_id = family_data.get("id")
    if family_id in by_id:
        try:
            confidence = max(0, min(100, int(family_data.get("confidence", 50))))
        except (TypeError, ValueError):
            confidence = 50
        guess = FamilyGuess(
            family_id=family_id,
            family_code=by_id[family_id],
            confidence=confidence,
            reason=str(family_data.get("reason", ""))[:200],
        )

    changes: list[SuggestedFieldChange] = []
    seen_keys: set[str] = set()
    for row in data.get("changes", []):
        if not isinstance(row, dict):
            continue
        key = row.get("field_key")
        value = row.get("new_value")
        if key not in valid_fields or not value or key in seen_keys:
            continue
        seen_keys.add(key)
        label = dict(TRANSCRIPT_EDITABLE_FIELDS)[key]
        changes.append(
            SuggestedFieldChange(
                field_key=key,
                label=label,
                new_value=str(value).strip(),
                reason=str(row.get("reason", ""))[:200],
            )
        )

    return TranscriptAnalysis(family_guess=guess, field_changes=changes)


class TranscriptLLM(ABC):
    @abstractmethod
    def analyse_transcript(
        self,
        transcript: str,
        candidate_families: list[tuple[int, str, str, str | None]],
    ) -> TranscriptAnalysis: ...


class MockTranscriptLLM(TranscriptLLM):
    """No network call. Looks for a candidate's name inside the transcript."""

    def analyse_transcript(
        self,
        transcript: str,
        candidate_families: list[tuple[int, str, str, str | None]],
    ) -> TranscriptAnalysis:
        lowered = transcript.lower()
        for fid, code, name, _district in candidate_families:
            first_name = name.split()[0].lower() if name else ""
            if first_name and first_name in lowered:
                return TranscriptAnalysis(
                    family_guess=FamilyGuess(
                        family_id=fid,
                        family_code=code,
                        confidence=70,
                        reason=f"The transcript mentions '{name.split()[0]}'",
                    ),
                    field_changes=[],
                )
        return TranscriptAnalysis(family_guess=None, field_changes=[])


class GeminiTranscriptLLM(TranscriptLLM):
    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise ValueError(
                "LLM_PROVIDER is set to gemini but LLM_API_KEY is empty."
            )
        self.api_key = api_key
        self.model = (model or "").strip() or DEFAULT_GEMINI_MODEL
        self.timeout = timeout

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc)
        if self.api_key:
            text = text.replace(self.api_key, "***")
        return re.sub(r"(key=)[^&\s'\"]+", r"\1***", text)

    def analyse_transcript(
        self,
        transcript: str,
        candidate_families: list[tuple[int, str, str, str | None]],
    ) -> TranscriptAnalysis:
        prompt = build_transcript_prompt(transcript, candidate_families)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
            },
        }
        try:
            response = httpx.post(
                GEMINI_URL.format(model=self.model),
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001 - never let this break a save
            logger.warning(
                "Gemini could not be reached for a transcript (%s); carrying on without it.",
                self._safe_error(exc),
            )
            return TranscriptAnalysis(family_guess=None, field_changes=[])

        return parse_transcript_response(text, candidate_families)


def get_transcript_llm() -> TranscriptLLM | None:
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off"}:
        return None
    if provider == "mock":
        return MockTranscriptLLM()
    if provider == "gemini":
        return GeminiTranscriptLLM(
            settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not built yet.")


def get_llm() -> LLM | None:
    """None means "do not use an LLM at all"."""
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off"}:
        return None
    if provider == "mock":
        return MockLLM()
    if provider == "gemini":
        return GeminiLLM(
            settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
    raise NotImplementedError(
        f"LLM provider '{settings.llm_provider}' is not built yet. "
        "Use 'mock', 'gemini', or 'none'."
    )
