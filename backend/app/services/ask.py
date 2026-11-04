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
families (one row per deceased soldier's family)
  id, family_code (e.g. AP-2026-0006), soldier_id -> soldiers.id,
  primary_contact_name (the widow / next of kin, NOK), nok_relationship (wife, mother...),
  primary_phone, alternate_phone, email, whatsapp_opted_in (bool),
  preferred_language (hindi, english, tamil, punjabi, malayalam, bengali, marathi),
  address_line, village_or_town (holds the VILLAGE), town, tehsil, post_office,
  district, state, pincode, gps_coordinates (text),
  ppo_number, bank_account_number, bank_ifsc, bank_name, bank_branch,
  co_unit_name, co_unit_phone, monthly_pension_amount (rupees), annual_income (rupees),
  extra_fields (jsonb), is_draft (bool; drafts are half-known families, leave them out unless asked),
  last_verified_on (date), last_contacted_on (date), notes

family_members (the widow, children, parents of a family)
  id, family_id -> families.id, full_name,
  relation (widow, son, daughter, father, mother, other_dependent),
  date_of_birth, gender, is_studying, education_level, is_married, marital_status,
  is_employed, has_disability, current_class, school_name, school_place, school_board,
  is_hostel, notes

soldiers (the soldier who died)
  id, full_name, rank, service_number, regiment, unit, date_of_birth, date_of_enrolment,
  date_of_death, cause_category (battle_casualty, physical_casualty, accident, illness,
  suicide, natural_causes, other), cause_sub_category, place_of_death, district_of_death,
  state_of_death, weather_at_death, duty_status (on_duty, on_leave, unknown), notes
  cause_sub_category is free text, e.g. 'Two-wheeler road accident', 'Vehicle accident on duty',
  'Electrocution', 'Avalanche', 'IED blast', 'Tuberculosis', 'Cancer', 'Stroke' (match with ILIKE).
  weather_at_death values: Clear, Cloudy, Rain, Dense fog, Extreme cold, Thunderstorm,
  Heat wave, Heavy snowfall.
  There is no season column: work it out from the month of date_of_death
  (winter = December, January, February).

postings (where a soldier, or one of our officers, served)
  id, soldier_id -> soldiers.id (or null), user_id -> users.id (or null),
  unit, formation, place, state, from_year, to_year

users (the colonel and his officers)
  id, full_name, rank, role (admin, colonel, officer, volunteer)

schemes (grants and schemes; all MOCK for now)
  id, code, name, authority, category (education, medical, ...), benefit_amount (rupees),
  is_recurring, is_active

applications (a family's application to a scheme)
  id, reference_code, family_id -> families.id, scheme_id -> schemes.id,
  stage (form_filled, verified_signed, submitted, received, money_credited, rejected),
  stage_changed_on (date), stuck_after_days (int; stuck when today - stage_changed_on
  is more than this and stage is not money_credited or rejected),
  ksb_dak_id, amount_claimed, amount_credited, credited_on, rejection_reason, notes

family_scheme_eligibility (which family can get which scheme)
  family_id, scheme_id, status (eligible, not_eligible, eligible_later, needs_data),
  becomes_eligible_on (date)

interactions (calls and voice notes with a family)
  id, family_id, interaction_type (phone_call, voice_note, field_visit), occurred_at (timestamp), language,
  summary_english, follow_up_needed (bool), follow_up_note
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
    """`failed` is (sql, database error) from a first attempt, so the model can fix it."""
    retry = (
        f"""

YOUR PREVIOUS QUERY FAILED. Fix it.
Query: {failed[0]}
Database error: {failed[1]}"""
        if failed
        else ""
    )
    return f"""You are the assistant in a welfare office run by a retired Indian Army colonel.
It supports the families of soldiers who have died. You answer his questions about
the families by choosing ONE tool. You never see the data itself: when you search,
the office's own software runs your query and shows him the rows.

TABLES:
{SCHEMA}

TOOLS (reply with exactly one, as JSON):
1. search — run one read-only PostgreSQL query over the tables above:
   {{"tool": "search", "title": "<short line describing the answer>", "sql": "<the query>"}}
2. cea — eligibility for the Children Education Allowance. ALWAYS use this for any
   CEA question (who can claim, how many, how much, is X eligible); eligibility is
   not a stored column, so writing SQL for it will be wrong. `year` is optional,
   e.g. "2025-26" or "2028"; leave it out for the most recently completed academic
   year. `name` is for ONE family ("is Meena Dagar eligible for CEA?"): the widow's
   or soldier's name, or a family code; leave it out to list every child who can claim:
   {{"tool": "cea", "year": "<academic year, or omit>", "name": "<one family, or omit>"}}
3. family — full details of ONE named family (its members and how to reach them),
   for "tell me about X", "X's family", "details of X", "who are X's children":
   {{"tool": "family", "name": "<the name or family code, as typed>"}}
4. reply — a short plain-English message, for greetings, thanks, "what can you do?",
   or when the data truly cannot answer (say what it does hold instead):
   {{"tool": "reply", "message": "<one to three short sentences>"}}
5. clarify — ask back ONLY when there is no sensible reading of the question AT ALL
   (see "WHEN TO GUESS INSTEAD OF ASKING" below), with 2 to 4 short choices he can
   click (each a complete question):
   {{"tool": "clarify", "message": "<the question back>", "options": ["...", "..."]}}

WHEN TO GUESS INSTEAD OF ASKING:
- Most short questions have an obvious everyday reading. Take it, and say what you
  assumed in the title, rather than using clarify. Examples:
  "names with A" -> widow / NOK names starting with A (note: "I took 'names' to
  mean widow / NOK names").
  "kids studying" -> children (son/daughter) with is_studying = true.
  "families in Moga" -> families.district ILIKE 'Moga'.
- Use clarify only when the question gives no topic to work with at all, e.g. a
  single word like "list" or "show", or two genuinely different readings that
  would give very different answers with no obvious winner.

NAME MATCHING:
- A colonel may type a name with a different spelling, only a first name, or
  missing capitals. Never require an exact match: split the name into words and
  require each word to appear somewhere with ILIKE, e.g. for "ramesh kumar":
  name ILIKE '%ramesh%' AND name ILIKE '%kumar%'.

FOLLOW-UP QUESTIONS:
- "how about X?", "and X?", "what about X?" mean: ask the MOST RECENT question
  again, with the same tool, for X instead. E.g. after "how many kids does Meena
  Dagar have?", "how about Archana Pawar?" is the same children search for Archana
  Pawar; after "is Meena Dagar eligible for CEA", it is the cea tool with name
  "Archana Pawar". Always follow the most recent question, not an older one.
- "she", "her", "he", "this family" mean the family in the most recent question.
- Read the conversation below. "them", "those", "these", "list them", "only in Punjab",
  "show their phones", "sort by district" refer to the most recent search.
- For a follow-up, start from that earlier query and change it: turn a count into a
  list, add a filter, add columns, change the order. Keep its other conditions.

SEARCH RULES (tool 1 only):
- Write a single SELECT (a WITH ... SELECT is fine). Never change data.
- Today is {today.isoformat()}.
- Leave out draft families (families.is_draft = true) unless asked about drafts.
- Name matching should ignore capital letters (use ILIKE).
- "Widow name" means families.primary_contact_name (no join needed).
- Ages: a person turns N on date_of_birth + interval 'N years'. For example
  "turning 18 in the next 3 months" is
  date_of_birth + interval '18 years' BETWEEN current_date AND current_date + interval '3 months'.
  Use current_date rather than writing today's date into the query.
- Join each table only once unless you really need it twice.
- Columns with a fixed list of values shown in brackets (relation, stage, language,
  cause_category, duty_status, role, status, interaction_type) are enums: compare them
  with = or IN using the exact lowercase value, never ILIKE.
- Use IN (...) for a choice of values, e.g. relation IN ('son', 'daughter'), and put
  brackets around any OR, so it cannot swallow the other conditions.
- Give every output column a short readable English alias in double quotes,
  e.g. AS "Widow name". Prefer names, district and family_code over ids.
- For a "how many" question that also says "list", return the list; the screen
  shows the count. For a pure "how many", return one row with the number.
- Order lists sensibly (usually by name).

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
    name: str | None = None  # for "family"


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
    # Set when one of our own tools answered (CEA, a family); kept in the chat
    # history so a follow-up knows what was asked. Never contains rows.
    tool: str | None = None


def error(text_: str, sql: str | None = None) -> Answer:
    return Answer(kind="error", error=text_, sql=sql)


NOT_UNDERSTOOD = "I did not understand the reply from the AI. Please try again."


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
        return Plan(tool="search", sql=str(data["sql"]), title=str(data.get("title") or "Answer"))
    if tool == "cea":
        year, name = data.get("year"), data.get("name")
        return Plan(
            tool="cea",
            year=str(year).strip() if year else None,
            name=str(name).strip() if name else None,
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
    'SELECT f.primary_contact_name AS "Widow / NOK name", '
    'f.district AS "District", f.state AS "State", '
    'f.family_code AS "Family code" '
    "FROM families f WHERE NOT f.is_draft "
    "AND f.primary_contact_name ILIKE '{ch}%' "
    "ORDER BY f.primary_contact_name"
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
                sql='SELECT count(*) AS "Families" FROM families WHERE NOT is_draft',
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
        try:
            response = httpx.post(
                GEMINI_URL.format(model=self.model),
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001 - shown to the colonel as a plain message
            logger.warning("Gemini could not answer a question (%s).", self._safe_error(exc))
            return Plan(tool="error", message="I could not reach the AI just now. Please try again.")
        return parse_plan(raw)


def get_question_llm() -> QuestionLLM | None:
    provider = settings.llm_provider.lower()
    if provider in {"", "none", "off"}:
        return None
    if provider == "mock":
        return MockQuestionLLM()
    if provider == "gemini":
        return GeminiQuestionLLM(
            settings.llm_api_key, settings.llm_model, settings.llm_timeout_seconds
        )
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
    """Run inside a read-only transaction that is always rolled back."""
    session.rollback()  # start a fresh transaction so the settings below apply to it
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        result = session.execute(text(f"SELECT * FROM ({sql}) AS answer LIMIT {MAX_ROWS + 1}"))
        columns = list(result.keys())
        rows = [[_cell(v) for v in row] for row in result.fetchall()]
    finally:
        session.rollback()
    truncated = len(rows) > MAX_ROWS
    return columns, rows[:MAX_ROWS], truncated


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

    today = today or date.today()
    history = (history or [])[-MAX_HISTORY:]
    failed: tuple[str, str] | None = None
    # A first query that the database rejects (a typo, a wrong type) gets one
    # retry, with the error shown to the LLM. The error names columns, not data.
    for _attempt in range(2):
        plan = llm.plan(question, today, history, failed)
        if plan.tool == "error":
            return error(plan.message or "Something went wrong.")
        if plan.tool == "reply":
            return Answer(kind="message", message=plan.message)
        if plan.tool == "clarify":
            return Answer(kind="clarify", message=plan.message, options=plan.options)
        if plan.tool == "cea":
            from app.services.tools import cea_tool  # local import: avoids a import cycle

            return cea_tool(session, plan.year, today, plan.name)
        if plan.tool == "family":
            from app.services.tools import family_tool  # local import: avoids a import cycle

            return family_tool(session, plan.name or "", today)

        try:
            sql = check_sql(plan.sql or "")
        except ValueError as exc:
            logger.warning("Refused a generated query: %s | %s", exc, plan.sql)
            return error(f"I could not run that safely. {exc}", plan.sql)

        try:
            columns, rows, truncated = run_query(session, sql)
            break
        except DBAPIError as exc:
            reason = str(exc.orig).strip().splitlines()[0] if exc.orig else str(exc)
            logger.warning("A generated query failed: %s | %s", reason, sql)
            failed = (sql, reason)
    else:
        return error("The search did not work. Try asking in a different way.", sql)

    return Answer(
        kind="table",
        title=plan.title or "Answer",
        columns=columns,
        rows=rows,
        count=len(rows),
        truncated=truncated,
        sql=sql,
    )
