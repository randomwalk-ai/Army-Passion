"""Answering a typed question about the data ("how many widows' names start with A?").

How it works:
1. The question and a description of our tables go to the LLM.
2. The LLM writes ONE read-only SQL query.
3. We check the query, run it inside a read-only transaction with a time
   limit, and send the rows back to the screen.

PRIVACY: only the question and the table/column NAMES go to the LLM. The rows
the query returns stay on this machine; they are never sent back to the LLM.

SAFETY: the LLM's SQL is never trusted. It must be a single SELECT, it runs in
a READ ONLY transaction (PostgreSQL itself refuses any change), it is stopped
after a few seconds, and only the first MAX_ROWS rows are fetched.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm import DEFAULT_GEMINI_MODEL, GEMINI_URL

logger = logging.getLogger(__name__)

MAX_ROWS = 1000
STATEMENT_TIMEOUT_MS = 5000
MAX_QUESTION_LENGTH = 1000

# What the LLM is told about the database. Written by hand rather than read
# from the models, so we choose what it sees and can explain the odd names.
SCHEMA = """
families: one row per family of a soldier who died (drafts already left out)
  family_code (e.g. AP-2026-0006), widow_name (the widow or next of kin, NOK),
  relationship (wife, mother, father...), phone, other_phone, email,
  language (hindi, english, tamil, punjabi, malayalam, bengali, marathi), whatsapp_opted_in,
  village, town, tehsil, post_office, district, state, pincode,
  bank_name, bank_branch, bank_account_number, bank_ifsc, has_bank_account (true/false),
  ppo_number, monthly_pension, annual_income (rupees),
  children_count, last_contacted_on (date), days_since_contact, last_verified_on,
  soldier_name, soldier_rank, service_number, regiment, unit, date_of_death,
  cause (battle casualty, physical casualty, accident, illness, suicide, natural causes, other),
  cause_detail (free text, e.g. 'Two-wheeler road accident', 'IED blast', 'Cancer'),
  co_unit_name, co_unit_phone, notes

children: one row per child (son, daughter, other dependent) of a family
  child_name, relation (son, daughter, other dependent), gender (male, female),
  date_of_birth, age (today), turns_18_on (date),
  is_studying, education (as written, e.g. 'Class 12', 'B.A. 1st year', 'ITI', 'Not studying'),
  class_number (0 = KG, 1-12 = school class, 13 = after school: college, ITI, diploma;
                -1 = not studying; empty = not known),
  school_name, is_hostel, has_disability, marital_status, is_married, is_employed,
  family_code, widow_name, phone, district, state,
  cea_year (the academic year that can be claimed now, e.g. '2025-26'),
  cea_status ('eligible', 'not eligible', 'eligible later', 'details missing') for cea_year,
  cea_reason (why, in plain words), cea_amount (rupees for that whole year, if eligible)

cea: Children Education Allowance for each child for several academic years
  family_code, widow_name, district, state, child_name,
  academic_year (e.g. '2024-25' ... '2028-29'), status ('eligible', 'not eligible',
  'eligible later', 'details missing'), reason, amount (rupees for that year),
  age_at_start (age when that year began), class_number

members: everyone in a family (widow, children, parents)
  name, relation (widow, son, daughter, father, mother, other dependent), gender,
  date_of_birth, age, marital_status, is_married, is_employed, has_disability,
  family_code, widow_name, phone, district, state

applications: a family's application to a scheme
  reference, family_code, widow_name, district, state, scheme, scheme_category,
  stage (form filled, verified signed, submitted, received, money credited, rejected),
  stage_since (date), days_in_stage, is_stuck (true/false: waiting longer than allowed),
  amount_claimed, amount_credited, credited_on, ksb_dak_id, rejection_reason

deaths: one row per soldier who died
  family_code, soldier_name, rank, regiment, unit, service_number, date_of_death,
  year, month (1-12), month_name, season (winter = Dec-Feb, summer = Mar-May,
  monsoon = Jun-Sep, post-monsoon = Oct-Nov), cause (as in families), cause_detail,
  place_of_death, district_of_death, state_of_death,
  weather (Clear, Cloudy, Rain, Dense fog, Extreme cold, Thunderstorm, Heat wave, Heavy snowfall),
  duty_status (on duty, on leave, unknown), family_district, family_state

calls: phone calls, voice notes and visits with a family
  family_code, widow_name, district, type (phone call, voice note, whatsapp message,
  field visit), date, language, summary, follow_up_needed, follow_up_note

postings: where soldiers, and the colonel and his officers, served
  person_type ('soldier' or 'officer'), person_name, rank, unit, formation, place,
  state, from_year, to_year, family_code (for a soldier)

schemes: grants and schemes (mostly MOCK for now)
  name, code, category (education, medical, ...), authority, benefit_amount, is_recurring, is_active

eligibility: which family can get which scheme (other than CEA)
  family_code, widow_name, district, scheme,
  status (eligible, not eligible, eligible later, needs data), becomes_eligible_on

problems: data problems found (missing phone, wrong date, possible duplicate...)
  family_code, widow_name, district, problem, severity (low, medium, high),
  status (open, resolved, ignored), description

documents: documents on record for a family
  family_code, widow_name, district, person, document_type, status, is_supporting, added_on
""".strip()


# How much of the conversation is sent with each question.
MAX_HISTORY = 10
MAX_HISTORY_SQL = 2000


@dataclass
class Turn:
    """One earlier question in this chat, as the LLM may see it.

    PRIVACY: only what the colonel typed and what the LLM itself wrote (a
    title, a query, a reply) — never the rows that came back.
    """

    question: str
    title: str | None = None
    sql: str | None = None
    reply: str | None = None
    # Which of our own tools answered, and for whom, e.g. "cea for family
    # AP-2026-0093 (Meena Dagar), year 2025-26" — so "how about X?" works.
    tool: str | None = None


def _history_text(history: list[Turn]) -> str:
    if not history:
        return "(this is the first question)"
    lines = []
    for n, turn in enumerate(history[-MAX_HISTORY:], 1):
        lines.append(f"{n}. Colonel asked: {turn.question}")
        if turn.sql:
            lines.append(f"   You searched ({turn.title or 'answer'}): {turn.sql[:MAX_HISTORY_SQL]}")
        elif turn.tool:
            lines.append(f"   You used the tool: {turn.tool}")
        elif turn.reply:
            lines.append(f"   You replied: {turn.reply}")
        elif turn.title:
            # A suggestion or a CEA/family answer: our own search, not one you wrote.
            lines.append(f"   The office software showed: {turn.title}")
    return "\n".join(lines)


def _latest_text(history: list[Turn]) -> str:
    """The most recent question, restated next to the new one: "how about X?"
    must repeat THIS question, and a small model can lose track in a long chat."""
    if not history:
        return ""
    last = history[-1]
    how = (
        f"the tool: {last.tool}" if last.tool
        else f"a search ({last.title})" if last.sql
        else "a reply"
    )
    return (
        f"MOST RECENT QUESTION (a follow-up like \"how about X?\" repeats this one): "
        f"{last.question!r}, answered with {how}.\n"
    )


def build_prompt(
    question: str,
    today: date,
    history: list[Turn] | None = None,
    failed: tuple[str, str] | None = None,
) -> str:
    """`failed` is (sql, what went wrong) from a first attempt, so the model can fix it.

    What went wrong is a database error, or "it found no rows": never the rows.
    """
    retry = (
        f"""

YOUR PREVIOUS QUERY NEEDS ANOTHER LOOK.
Query: {failed[0]}
What happened: {failed[1]}
Fix the query if a column, table or value was wrong. If it was right and there
really is nothing to find, send the same query again."""
        if failed
        else ""
    )
    return f"""You are the assistant in a welfare office run by a retired Indian Army colonel.
It supports the families of soldiers who have died. You answer his questions about
the families by choosing ONE tool. You never see the data itself: when you search,
the office's own software runs your query and shows him the rows.

TABLES (these are the only tables there are; use them exactly as named):
{SCHEMA}

TOOLS (reply with exactly one, as JSON):
1. search — one read-only PostgreSQL query over the tables above:
   {{"tool": "search",
     "understood": "<one plain sentence: what you looked for, e.g. 'Children who can claim CEA for 2025-26, in Class 9 to 12, the 10 families with the highest classes'>",
     "title": "<short heading for the answer>",
     "sql": "<the query>"}}
2. family — full details of ONE named family, for "tell me about X", "X's family",
   "details of X":
   {{"tool": "family", "name": "<the name or family code, as typed>"}}
3. reply — a short plain-English message, for greetings, thanks, "what can you do?",
   or when the data truly cannot answer (say what it does hold instead):
   {{"tool": "reply", "message": "<one to three short sentences>"}}
4. clarify — ask back ONLY when there is no sensible reading of the question AT ALL,
   with 2 to 4 short choices he can click (each a complete question):
   {{"tool": "clarify", "message": "<the question back>", "options": ["...", "..."]}}

CEA (Children Education Allowance):
- Eligibility is already worked out: use children.cea_status / cea_amount for the year
  that can be claimed now, and the cea table for any other academic year
  ("by 2028" -> academic_year '2027-28' or '2028-29', say which in "understood").
- "Is X eligible for CEA?" -> that family's children with their status and reason.
- "Which 10 families should I fill first, children going into 10th and 12th" ->
  eligible children with class_number IN (9, 10, 11, 12), highest class first,
  only the first 10 families.

WHEN TO GUESS INSTEAD OF ASKING:
- Most short questions have an obvious everyday reading: take it, and say what you
  assumed in "understood". "names with A" -> widow names STARTING with A
  (widow_name ILIKE 'a%'), not names containing an a.
  "kids studying" -> children with is_studying. "families in Moga" -> district 'Moga'.
- Use clarify only when there is no topic at all ("list", "show") or two readings that
  give very different answers with no obvious winner.

NAME MATCHING:
- Names may be spelled differently, given in part, or in any capitals. Split the name
  into words and require each word with ILIKE: for "ramesh kumar",
  widow_name ILIKE '%ramesh%' AND widow_name ILIKE '%kumar%'. A family can be named by
  the widow, the soldier (soldier_name) or its family_code.
- Place names too: district ILIKE '%moga%' (a misspelling like 'Mogaa' -> '%moga%').

FOLLOW-UP QUESTIONS:
- "how about X?", "and X?", "what about X?" mean: ask the MOST RECENT question again,
  for X instead (same tool, same kind of search).
- "she", "her", "this family" mean the family in the most recent question.
- "them", "those", "list them", "only in Punjab", "show their phones", "sort by
  district" change the most recent search: start from its query and change it
  (count -> list, add a filter, add columns, change the order). Keep its other conditions.

SEARCH RULES:
- A single SELECT (a WITH ... SELECT is fine). Never change data. Use only the tables
  above, without a schema name in front of them.
- Today is {today.isoformat()}. Use current_date in the query rather than a written date.
- "turning 18 in the next 3 months": turns_18_on BETWEEN current_date AND current_date + interval '3 months'.
- Text matching ignores capitals: ILIKE. The values listed in brackets above are the
  exact words stored: compare with = or IN.
- Put brackets around any OR so it cannot swallow the other conditions.
- Give every column a short readable alias in double quotes, e.g. AS "Widow name".
  Show names, district and family_code rather than bare numbers.
- "how many ... list them" -> return the list (the screen shows the count).
  A pure "how many" -> one row with the number.
- Order lists sensibly (usually by name, or by the thing asked about).
- Filter only on what he asked. Do not add conditions of your own (is_studying,
  a status, "verified", a year) unless the question needs them: "children in class 12"
  is class_number = 12 and nothing else; "death certificates" is every death certificate.
- "how many X" counts X itself (documents, children, calls), not the families they
  belong to, unless he asks how many families.
- Never add LIMIT unless he asks for a number of results ("top 10", "first 5"): the
  screen shows every row and says how many there are.

CONVERSATION SO FAR:
{_history_text(history or [])}
{_latest_text(history or [])}
QUESTION: {question}{retry}"""


@dataclass
class Plan:
    """The tool the LLM chose, and what to do with it."""

    # "search", "cea", "family", "reply", "clarify", or "error" when the LLM
    # itself could not be reached.
    tool: str
    sql: str | None = None
    title: str | None = None
    message: str | None = None
    options: list[str] = field(default_factory=list)
    year: str | None = None  # for "cea"
    name: str | None = None  # for "family", or one family for "cea"
    classes: list[int] = field(default_factory=list)  # for "cea": only these classes
    limit: int | None = None  # for "cea": only this many families
    # One plain sentence saying what the search looks for, shown above the answer.
    understood: str | None = None


@dataclass
class Answer:
    # "table" (search results), "message" (a plain reply), "clarify" (a
    # question back, with options) or "error" (something went wrong).
    kind: str
    title: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    count: int = 0
    truncated: bool = False
    sql: str | None = None
    message: str | None = None
    options: list[str] = field(default_factory=list)
    error: str | None = None
    # "I looked for: ...", shown above the answer so a misunderstanding shows.
    understood: str | None = None
    # Set when one of our own tools answered (CEA, a family); kept in the chat
    # history so a follow-up knows what was asked. Never contains rows.
    tool: str | None = None


def error(text_: str, sql: str | None = None) -> Answer:
    return Answer(kind="error", error=text_, sql=sql)


NOT_UNDERSTOOD = "I did not understand the reply from the AI. Please try again."
UNREACHABLE = "I could not reach the AI just now. Please try again in a minute."
BUSY_WAIT_SECONDS = 1.5


def parse_plan(raw: str) -> Plan:
    cleaned = raw.strip()
    # Some models wrap JSON in ```json fences even when told not to.
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return Plan(tool="error", message=NOT_UNDERSTOOD)
    if not isinstance(data, dict):
        return Plan(tool="error", message=NOT_UNDERSTOOD)

    tool = str(data.get("tool") or ("search" if data.get("sql") else "reply"))
    if tool == "search" and data.get("sql"):
        understood = data.get("understood")
        return Plan(
            tool="search",
            sql=str(data["sql"]),
            title=str(data.get("title") or "Answer"),
            understood=str(understood).strip() if understood else None,
        )
    if tool == "cea":
        year, name = data.get("year"), data.get("name")
        classes = [
            int(c) for c in data.get("classes") or []
            if isinstance(c, (int, float, str)) and str(c).strip().isdigit()
        ]
        limit = data.get("limit")
        return Plan(
            tool="cea",
            year=str(year).strip() if year else None,
            name=str(name).strip() if name else None,
            classes=classes,
            limit=int(limit) if isinstance(limit, (int, float)) and limit > 0 else None,
        )
    if tool == "family" and data.get("name"):
        return Plan(tool="family", name=str(data["name"]))
    if tool == "clarify":
        options = [str(o) for o in data.get("options") or [] if str(o).strip()][:4]
        return Plan(
            tool="clarify",
            message=str(data.get("message") or "Could you say a bit more?"),
            options=options,
        )
    message = data.get("message") or data.get("cannot_answer")
    if not message:
        return Plan(tool="error", message=NOT_UNDERSTOOD)
    return Plan(tool="reply", message=str(message))


# --- the LLM, behind an interface ----------------------------------------------


class QuestionLLM(ABC):
    @abstractmethod
    def plan(
        self,
        question: str,
        today: date,
        history: list[Turn] | None = None,
        failed: tuple[str, str] | None = None,
    ) -> Plan:
        """Choose a tool for the question.

        `history` is the conversation so far; `failed` is (sql, database error)
        when a first attempt did not run.
        """


MOCK_LETTER = (
    'SELECT widow_name AS "Widow / NOK name", '
    'district AS "District", state AS "State", '
    'family_code AS "Family code" '
    "FROM families WHERE widow_name ILIKE '{ch}%' "
    "ORDER BY widow_name"
)
MOCK_COUNT = re.compile(r'^SELECT count\(\*\) AS "[^"]*" FROM \((.*)\) AS x$', re.S)


class MockQuestionLLM(QuestionLLM):
    """Answers a few question shapes with no network, for tests and offline work."""

    def plan(
        self,
        question: str,
        today: date,
        history: list[Turn] | None = None,
        failed: tuple[str, str] | None = None,
    ) -> Plan:
        q = question.strip().lower()
        if re.fullmatch(r"(hi|hello|namaste|thanks|thank you)[.! ]*", q):
            return Plan(tool="reply", message="Hello! Ask me anything about the families.")

        if "cea" in q:
            year = re.search(r"(?<![\w-])(20\d{2}(?:-\d{2,4})?)(?![\w-])", q)
            who = re.search(r"\bis\s+(.+?)\s+eligible", q)
            return Plan(
                tool="cea",
                year=year.group(1) if year else None,
                name=who.group(1) if who else None,
            )

        about = re.search(
            r"(?:about|details? of|family of|tell me about)\s+([a-z][a-z .]{2,40})\b",
            q,
        )
        if about:
            return Plan(tool="family", name=about.group(1).strip())

        letter = re.search(
            r"(?:start(?:s|ing)?\s+with|names?\s+with)\s+(?:the\s+)?(?:letter\s+)?"
            r"[\"'“‘]?([A-Za-z])\b",
            question,
            re.IGNORECASE,
        )
        if letter:
            ch = letter.group(1).upper()
            sql = MOCK_LETTER.format(ch=ch)
            if q.startswith("how many") and "list" not in q:
                sql = f'SELECT count(*) AS "Families" FROM ({sql}) AS x'
            return Plan(tool="search", title=f"Widow / NOK names starting with “{ch}”", sql=sql)

        # "list them" after a count: the same search, as a list.
        last = next((t for t in reversed(history or []) if t.sql), None)
        if last and re.fullmatch(r"(list|show)( them| those| these)?[.! ]*", q):
            inner = MOCK_COUNT.match(last.sql)
            return Plan(tool="search", title=last.title, sql=inner.group(1) if inner else last.sql)

        if re.search(r"how many families", q):
            return Plan(
                tool="search",
                title="Number of families",
                sql='SELECT count(*) AS "Families" FROM families',
            )
        return Plan(
            tool="reply",
            message=(
                "The AI is switched off (LLM_PROVIDER=mock), so I can only answer a "
                "few fixed questions. Set LLM_PROVIDER=gemini in .env to ask anything."
            ),
        )


class GeminiQuestionLLM(QuestionLLM):
    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        if not api_key:
            raise ValueError("LLM_PROVIDER is set to gemini but LLM_API_KEY is empty.")
        self.api_key = api_key
        self.model = (model or "").strip() or DEFAULT_GEMINI_MODEL
        self.timeout = timeout

    def _safe_error(self, exc: Exception) -> str:
        """Never let the API key appear in a log line or an error message."""
        text_ = str(exc).replace(self.api_key, "***")
        return re.sub(r"(key=)[^&\s'\"]+", r"\1***", text_)

    def plan(
        self,
        question: str,
        today: date,
        history: list[Turn] | None = None,
        failed: tuple[str, str] | None = None,
    ) -> Plan:
        body = {
            "contents": [{"parts": [{"text": build_prompt(question, today, history, failed)}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        # Gemini sometimes answers "busy" (503) or "too many requests" (429) for
        # a moment; one short wait usually gets through.
        for attempt in range(2):
            try:
                response = httpx.post(
                    GEMINI_URL.format(model=self.model),
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                    timeout=self.timeout,
                )
                if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                    time.sleep(BUSY_WAIT_SECONDS)
                    continue
                response.raise_for_status()
                raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                return parse_plan(raw)
            except Exception as exc:  # noqa: BLE001 - shown to the colonel as a plain message
                logger.warning("Gemini could not answer a question (%s).", self._safe_error(exc))
                break
        return Plan(tool="unreachable", message=UNREACHABLE)


def get_question_llm(bigger: bool = False) -> QuestionLLM | None:
    """The LLM that turns questions into searches.

    `bigger` picks the larger Gemini model, tried once when the usual small
    one has failed: slower, but better at a question it got wrong twice.
    """
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off"}:
        return None
    if provider == "mock":
        return MockQuestionLLM()
    if provider == "gemini":
        model = settings.llm_fallback_model if bigger else settings.llm_model
        return GeminiQuestionLLM(settings.llm_api_key, model, settings.llm_timeout_seconds)
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not built yet.")


# --- checking and running the query ---------------------------------------------

# Words that have no place in a read-only question. The read-only transaction
# would refuse most of these anyway; this gives a clear message first.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|"
    r"vacuum|analyze|call|do|execute|prepare|set|reset|lock|listen|notify|"
    r"pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|lo_export|dblink)\b",
    re.IGNORECASE,
)
# The chatbot searches only the simple views in the "ask" schema: while a
# search runs nothing else is on the search path, so the only way to reach a
# raw table is to name its schema (public.users), and system tables start with
# pg_ or sit in information_schema. Those are refused.
PUBLIC_SCHEMA = re.compile(r"\bpublic\s*\.", re.IGNORECASE)
SYSTEM_NAMES = re.compile(r"\b(pg_[a-z0-9_]*|information_schema)\b", re.IGNORECASE)
# The views live here; nothing else is on the search path while a search runs.
SEARCH_SCHEMA = "ask"


def check_sql(sql: str) -> str:
    """Return the query ready to run, or raise ValueError with the reason."""
    cleaned = sql.strip().rstrip(";").strip()
    # Drop comments so a forbidden word cannot hide in one, and so the checks
    # below see the real query.
    cleaned = re.sub(r"--[^\n]*", " ", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL).strip()
    if ";" in cleaned:
        raise ValueError("The query had more than one statement.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("The query was not a plain search.")
    # Quoted text ('...') and aliases ("...") may contain any word; check the rest.
    bare = re.sub(r"'(?:[^']|'')*'|\"[^\"]*\"", "''", cleaned)
    bad = FORBIDDEN.search(bare)
    if bad:
        raise ValueError(f"The query used “{bad.group(1)}”, which is not allowed.")
    system = SYSTEM_NAMES.search(bare)
    if system:
        raise ValueError(f"The query looked at “{system.group(1)}”, which is not allowed.")
    if PUBLIC_SCHEMA.search(bare):
        raise ValueError("The query reached outside the chatbot's tables (public.).")
    return cleaned


def _cell(value: Any) -> Any:
    """Make a value safe for JSON, in Indian formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def run_query(session: Session, sql: str) -> tuple[list[str], list[list[Any]], bool]:
    """Run inside a read-only transaction that is always rolled back.

    Only the "ask" views are on the search path, so a table name in the query
    can only mean one of them, never a raw table.
    """
    session.rollback()  # start a fresh transaction so the settings below apply to it
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        session.execute(text(f"SET LOCAL search_path TO {SEARCH_SCHEMA}"))
        result = session.execute(text(f"SELECT * FROM ({sql}) AS answer LIMIT {MAX_ROWS + 1}"))
        columns = list(result.keys())
        rows = [[_cell(v) for v in row] for row in result.fetchall()]
    finally:
        session.rollback()
    truncated = len(rows) > MAX_ROWS
    return columns, rows[:MAX_ROWS], truncated


# What the LLM is told when a search found nothing, so it can check its work.
# Never the rows (there are none) and never any data.
NO_ROWS = (
    "It ran but found no rows. Check every filter: is the column right, and is the "
    "value one that is really stored (see the values listed with each table)?"
)


def _attempt(
    session: Session,
    llm: QuestionLLM,
    question: str,
    today: date,
    history: list[Turn],
    failed: tuple[str, str] | None,
) -> tuple[Answer | None, tuple[str, str] | None]:
    """One try: ask the LLM, carry out its choice.

    Returns (answer, None) when done, or (None, (sql, what went wrong)) when the
    search failed and is worth another try.
    """
    plan = llm.plan(question, today, history, failed)
    if plan.tool == "unreachable":
        # Busy or down: let the next try (and then the bigger model) have a go.
        return None, failed
    if plan.tool == "error":
        return error(plan.message or "Something went wrong."), None
    if plan.tool == "reply":
        return Answer(kind="message", message=plan.message), None
    if plan.tool == "clarify":
        return Answer(kind="clarify", message=plan.message, options=plan.options), None
    if plan.tool == "cea":
        from app.services.tools import cea_tool  # local import: avoids an import cycle

        return cea_tool(session, plan.year, today, plan.name, plan.classes, plan.limit), None
    if plan.tool == "family":
        from app.services.tools import family_tool  # local import: avoids an import cycle

        return family_tool(session, plan.name or "", today), None

    try:
        sql = check_sql(plan.sql or "")
    except ValueError as exc:
        logger.warning("Refused a generated query: %s | %s", exc, plan.sql)
        return error(f"I could not run that safely. {exc}", plan.sql), None

    try:
        columns, rows, truncated = run_query(session, sql)
    except DBAPIError as exc:
        reason = str(exc.orig).strip().splitlines()[0] if exc.orig else str(exc)
        logger.warning("A generated query failed: %s | %s", reason, sql)
        return None, (sql, reason)

    answer = Answer(
        kind="table",
        title=plan.title or "Answer",
        understood=plan.understood,
        columns=columns,
        rows=rows,
        count=len(rows),
        truncated=truncated,
        sql=sql,
    )
    return answer, None


def answer_question(
    session: Session,
    question: str,
    history: list[Turn] | None = None,
    today: date | None = None,
) -> Answer:
    question = question.strip()
    if not question:
        return error("Type a question first.")
    if len(question) > MAX_QUESTION_LENGTH:
        return error(f"Please keep the question under {MAX_QUESTION_LENGTH} letters.")

    llm = get_question_llm()
    if llm is None:
        return error("Questions need the AI, which is switched off (LLM_PROVIDER).")

    # CEA results and class numbers are worked out by our own code; make sure
    # they reflect the data as it is now (a no-op when nothing has changed).
    from app.services.derived import ensure_fresh  # local import: avoids an import cycle

    ensure_fresh(session)
    session.commit()

    today = today or date.today()
    history = (history or [])[-MAX_HISTORY:]

    # 1st try with the usual model. A search the database rejects, or one that
    # finds nothing, is shown back to the LLM (the error or "no rows", never
    # data) for a 2nd try. If that still fails, the bigger model has one go.
    failed: tuple[str, str] | None = None
    empty: Answer | None = None
    for model in (llm, llm, get_question_llm(bigger=True)):
        answer, failed_now = _attempt(session, model, question, today, history, failed)
        if answer is None:
            failed = failed_now
            continue
        if answer.kind == "table" and answer.count == 0 and empty is None and answer.sql:
            # Found nothing: worth one more look, in case a filter was wrong.
            empty = answer
            failed = (answer.sql, NO_ROWS)
            continue
        return answer
    if empty is not None:
        # Looked twice and there really is nothing (or the retry failed).
        return empty
    if failed is None:
        # Every try was "could not reach the AI", none got as far as a search.
        return error(UNREACHABLE)
    return error("The search did not work. Try asking in a different way.", failed[0])
