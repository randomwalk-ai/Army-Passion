"""Scores the chatbot against a bank of real questions.

This is NOT a pytest test: it calls the REAL Gemini (LLM_PROVIDER must be
"gemini" in .env), so it costs a little and needs internet. Run it by hand
after a change to the chatbot:

    backend\\.venv\\Scripts\\python.exe -m scripts.score_chatbot

Where a question has one right number, the bank works it out FROM THE
DATABASE at run time (a "truth" query over the same views the chatbot uses),
never a number typed by hand, so the score stays right as the data changes.
Other questions check the kind of answer (a table, a reply, a question back).
Questions marked wrong with 👎 on the Assistant screen belong here too: list
them with  GET /api/ask/feedback?rating=-1  and add each with its truth.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.services.ask import Answer, Turn, answer_question
from app.services.derived import ensure_fresh

Check = Callable[[object, Answer], bool]


def truth(session, sql: str) -> int:
    """One number from the chatbot's own views."""
    session.execute(text("SET LOCAL search_path TO ask"))
    return int(session.execute(text(sql)).scalar() or 0)


def count_is(sql: str) -> Check:
    """Right when the answer is that many rows, or one cell holding that number."""

    def check(session, answer: Answer) -> bool:
        if answer.kind != "table":
            return False
        want = truth(session, sql)
        if len(answer.rows) == 1 and len(answer.columns) == 1:
            return answer.rows[0][0] == want
        return answer.count == want

    return check


def count_in(*sqls: str) -> Check:
    """Like count_is, for a question with more than one fair reading."""

    def check(session, answer: Answer) -> bool:
        if answer.kind != "table":
            return False
        wants = {truth(session, sql) for sql in sqls}
        if len(answer.rows) == 1 and len(answer.columns) == 1:
            return answer.rows[0][0] in wants
        return answer.count in wants

    return check


def number_is(sql: str) -> Check:
    """Right when the answer contains that number (a total, a sum)."""

    def check(session, answer: Answer) -> bool:
        if answer.kind != "table" or not answer.rows:
            return False
        want = truth(session, sql)
        return any(cell == want for row in answer.rows for cell in row)

    return check


def table(session, answer: Answer) -> bool:
    return answer.kind == "table"


def table_with_rows(session, answer: Answer) -> bool:
    return answer.kind == "table" and answer.count > 0


def reply(session, answer: Answer) -> bool:
    return answer.kind == "message"


def reply_or_clarify(session, answer: Answer) -> bool:
    return answer.kind in ("message", "clarify")


def family_or_choices(session, answer: Answer) -> bool:
    return answer.kind in ("table", "clarify")


@dataclass
class Question:
    text: str
    check: Check
    area: str
    # Earlier questions in the same chat, for follow-ups.
    before: list[str] = field(default_factory=list)


Q = Question
QUESTIONS: list[Question] = [
    # --- families ---
    Q("how many families are there", count_is("SELECT count(*) FROM families"), "families"),
    Q("families in Moga", count_is("SELECT count(*) FROM families WHERE district ILIKE '%moga%'"), "families"),
    Q("families in Mogaa", count_is("SELECT count(*) FROM families WHERE district ILIKE '%moga%'"), "families"),
    Q("how many families live in Punjab", count_is("SELECT count(*) FROM families WHERE state ILIKE '%punjab%'"), "families"),
    Q("list names with A", count_is("SELECT count(*) FROM families WHERE widow_name ILIKE 'a%'"), "families"),
    Q('How many families have the widow name starting with letter "A" list them',
      count_is("SELECT count(*) FROM families WHERE widow_name ILIKE 'a%'"), "families"),
    Q("which families have no phone number", count_is(
        "SELECT count(*) FROM families WHERE phone IS NULL OR phone = ''"), "families"),
    Q("families without a bank account", count_is(
        "SELECT count(*) FROM families WHERE NOT has_bank_account"), "families"),
    Q("families not contacted in the last 6 months", count_in(
        "SELECT count(*) FROM families WHERE last_contacted_on < current_date - interval '6 months'",
        "SELECT count(*) FROM families WHERE days_since_contact > 180",
        "SELECT count(*) FROM families WHERE days_since_contact >= 180",
        "SELECT count(*) FROM families WHERE last_contacted_on IS NULL"
        " OR last_contacted_on < current_date - interval '6 months'",
        "SELECT count(*) FROM families WHERE last_contacted_on IS NULL OR days_since_contact > 180"),
      "families"),
    Q("families that speak Tamil", count_is("SELECT count(*) FROM families WHERE language = 'tamil'"), "families"),
    Q("details of AP-2026-0049", table_with_rows, "families"),
    Q("tell me about Paramjit Kaur", family_or_choices, "families"),

    # --- children ---
    Q("children turning 18 in the next 3 months", count_is(
        "SELECT count(*) FROM children WHERE turns_18_on BETWEEN current_date AND current_date + interval '3 months'"),
      "children"),
    Q("how many children are studying", count_is("SELECT count(*) FROM children WHERE is_studying"), "children"),
    Q("children in class 12", count_is("SELECT count(*) FROM children WHERE class_number = 12"), "children"),
    Q("how many children are in class 10 or class 12", count_in(
        "SELECT count(*) FROM children WHERE class_number IN (10, 12)",
        "SELECT count(*) FROM children WHERE class_number IN (10, 12) AND is_studying"), "children"),
    Q("children with a disability", count_is("SELECT count(*) FROM children WHERE has_disability"), "children"),
    Q("how many sons are there", count_is("SELECT count(*) FROM children WHERE relation = 'son'"), "children"),
    Q("children who are not studying", count_in(
        "SELECT count(*) FROM children WHERE is_studying = false",
        "SELECT count(*) FROM children WHERE is_studying = false OR class_number = -1"
        " OR education ILIKE '%not studying%'",
        "SELECT count(*) FROM children WHERE is_studying = false OR class_number = -1"), "children"),
    Q("how many families have 2 kids who are studying school", table, "children"),
    Q("how many kids does meena dagar have?", table_with_rows, "children"),

    # --- CEA ---
    Q("how many children can claim CEA this year", count_is(
        "SELECT count(*) FROM children WHERE cea_status = 'eligible'"), "cea"),
    Q("children eligible for CEA in 2027-28", count_is(
        "SELECT count(*) FROM cea WHERE academic_year = '2027-28' AND status = 'eligible'"), "cea"),
    Q("is meena dagar eligible for cea", table_with_rows, "cea"),
    Q("total CEA amount the families can claim this year", number_is(
        "SELECT sum(cea_amount) FROM children WHERE cea_status = 'eligible'"), "cea"),
    Q("which children need more details before CEA can be decided", count_is(
        "SELECT count(*) FROM children WHERE cea_status = 'details missing'"), "cea"),
    Q("children who will be able to claim CEA later", count_is(
        "SELECT count(*) FROM children WHERE cea_status = 'eligible later'"), "cea"),
    Q("i have to fill the cea for 10 families which 10 families should i fill first . focus mainly on the "
      "children who are gonna move to their 10 th and 12th grade so it wil be beneficial for them",
      table_with_rows, "cea"),
    Q("list the number of kids eligible for CEA by 2028", table, "cea"),

    # --- applications ---
    Q("how many applications are stuck", count_is("SELECT count(*) FROM applications WHERE is_stuck"), "applications"),
    Q("which applications have been stuck the longest", table_with_rows, "applications"),
    Q("applications where the money has been credited", count_is(
        "SELECT count(*) FROM applications WHERE stage = 'money credited'"), "applications"),
    Q("how many applications were rejected", count_is(
        "SELECT count(*) FROM applications WHERE stage = 'rejected'"), "applications"),
    Q("which schemes have the most applications", table_with_rows, "applications"),
    Q("total amount credited to families so far", number_is(
        "SELECT sum(amount_credited) FROM applications WHERE amount_credited IS NOT NULL"), "applications"),

    # --- deaths ---
    Q("how many soldiers died in winter", count_is("SELECT count(*) FROM deaths WHERE season = 'winter'"), "deaths"),
    Q("which districts in Punjab had road accidents in winter", table_with_rows, "deaths"),
    Q("how many battle casualties", count_is("SELECT count(*) FROM deaths WHERE cause = 'battle casualty'"), "deaths"),
    Q("how many soldiers died while on leave", count_is(
        "SELECT count(*) FROM deaths WHERE duty_status = 'on leave'"), "deaths"),
    Q("deaths in dense fog", count_is("SELECT count(*) FROM deaths WHERE weather = 'Dense fog'"), "deaths"),
    Q("number of deaths each year", table_with_rows, "deaths"),

    # --- calls, problems, documents, postings ---
    Q("calls that need a follow up", count_is("SELECT count(*) FROM calls WHERE follow_up_needed"), "calls"),
    Q("how many voice notes have we had", count_is("SELECT count(*) FROM calls WHERE type = 'voice note'"), "calls"),
    Q("how many open data problems are there", count_is(
        "SELECT count(*) FROM problems WHERE status = 'open'"), "problems"),
    Q("families with a missing phone problem", table, "problems"),
    Q("how many death certificates do we have", count_is(
        "SELECT count(*) FROM documents WHERE document_type = 'death certificate'"), "documents"),
    Q("where has the colonel served", table_with_rows, "postings"),

    # --- conversation ---
    Q("hi", reply, "conversation"),
    Q("what can you do?", reply, "conversation"),
    Q("what will the weather be like next week", reply_or_clarify, "conversation"),

    # --- follow-ups (asked after the questions in `before`) ---
    Q("list them", count_is("SELECT count(*) FROM families WHERE widow_name ILIKE 'a%'"), "follow-up",
      before=["how many widow names start with A"]),
    Q("only the ones in Tamil Nadu", count_is(
        "SELECT count(*) FROM families WHERE widow_name ILIKE 'a%' AND state ILIKE '%tamil%'"), "follow-up",
      before=["list widow names starting with A"]),
    Q("how about sunanda pawar?", table_with_rows, "follow-up", before=["is meena dagar eligible for cea"]),
    Q("how about sunanda pawar?", table_with_rows, "follow-up", before=["how many kids does meena dagar have?"]),
]


def ask_in_chat(session, question: Question) -> Answer:
    history: list[Turn] = []
    for earlier in question.before:
        first = answer_question(session, earlier, history)
        history.append(Turn(question=earlier, title=first.title, sql=first.sql,
                            reply=first.message, tool=first.tool))
    return answer_question(session, question.text, history)


def main() -> int:
    if settings.llm_provider.lower() != "gemini":
        print("Set LLM_PROVIDER=gemini in .env before running this script.")
        return 1

    session = SessionLocal()
    ensure_fresh(session)
    session.commit()
    passed = 0
    by_area: dict[str, list[int]] = {}
    failed: list[str] = []

    for q in QUESTIONS:
        answer = ask_in_chat(session, q)
        ok = bool(q.check(session, answer))
        session.rollback()
        passed += ok
        by_area.setdefault(q.area, [0, 0])
        by_area[q.area][0] += ok
        by_area[q.area][1] += 1
        shown = answer.understood or answer.title or answer.message or answer.error or ""
        print(f"[{'PASS' if ok else 'FAIL'}] {q.text[:70]!r} -> {answer.kind} | {shown[:90]}")
        if not ok:
            failed.append(q.text)

    print(f"\n{passed}/{len(QUESTIONS)} correct")
    for area, (good, total) in by_area.items():
        print(f"  {area:14} {good}/{total}")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f[:100]}")
    session.close()
    return 0 if passed == len(QUESTIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
