"""Scores the chatbot against a bank of real questions, including every
question the colonel actually typed while we were testing it.

This is NOT a pytest test: it calls the REAL Gemini (LLM_PROVIDER must be
"gemini" in .env), so it costs a little and needs internet. Run it by hand
after a change to the chatbot's instructions or tools:

    backend\\.venv\\Scripts\\python.exe -m scripts.score_chatbot

Each question has a `check` that works out the right answer FROM THE
DATABASE at run time (never a number typed by hand), so the score stays
correct as the mock data changes. A question passes when the chatbot's
answer matches what `check` says it should be.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Family
from app.services.ask import Answer, answer_question
from app.services.cea import AcademicYear, ELIGIBLE, ensure_cea_scheme, evaluate_family
from app.services.suggestions import stuck_count, turning_18_card

TODAY = date.today()


@dataclass
class Question:
    text: str
    # Returns True (passed), False (failed), or a short reason string for a
    # softer "looks reasonable" check that is reported but doesn't fail the run.
    check: Callable[[object, Answer], bool]
    note: str = ""


def _count_check(expected: Callable[[object], int]):
    def check(session, answer: Answer) -> bool:
        if answer.kind != "table":
            return False
        want = expected(session)
        got = answer.rows[0][0] if len(answer.rows) == 1 and len(answer.columns) == 1 else answer.count
        return got == want

    return check


def _is_table(session, answer: Answer) -> bool:
    return answer.kind == "table"


def _is_message(session, answer: Answer) -> bool:
    return answer.kind == "message"


QUESTIONS: list[Question] = [
    # --- the exact questions the colonel typed while testing ---
    Question(
        'How many families have the widow name starting with letter "A" list them',
        _count_check(lambda s: s.scalar(
            select(func.count()).select_from(Family)
            .where(Family.is_draft.is_(False), Family.primary_contact_name.ilike("A%"))
        )),
    ),
    Question("list names with A", _is_table),
    Question("list the number of kids eligible for CEA by 2028", _is_table),
    Question("how many families have 2 kids who are studying school", _is_table),
    Question("hi", _is_message),
    Question("what can you do?", _is_message),
    Question("tell me about Paramjit Kaur", lambda s, a: a.kind in ("clarify", "table")),
    Question("details of AP-2026-0049", _is_table),

    # --- follow-ups (need a first question in the same run; see run_followups) ---

    # --- CEA ---
    Question(
        "how many children can claim CEA this year",
        # "this year" is genuinely ambiguous: the currently running academic
        # year, or the last completed one (claims are filed after a year
        # ends, which is what the tool defaults to). Either is a fair answer.
        lambda s, a: a.kind == "table" and a.count in (_cea_count(s, None), _cea_count_current(s)),
        note="either the current or the last-completed academic year is acceptable",
    ),
    Question(
        "children eligible for CEA in 2025-26",
        lambda s, a: a.kind == "table" and a.count == _cea_count(s, "2025-26"),
    ),

    # --- stuck / turning 18 (compare with the suggestion cards' own numbers) ---
    Question(
        "how many applications are stuck",
        _count_check(lambda s: stuck_count(s, TODAY)),
    ),
    Question(
        "which children are turning 18 in the next 3 months",
        lambda s, a: (
            a.kind == "table"
            and (card := turning_18_card(s, TODAY)) is not None
            and a.count == card.count
        ),
    ),

    # --- things it should refuse, not guess at ---
    Question(
        "which districts had road accidents in winter",
        lambda s, a: a.kind == "table",  # answerable: cause_sub_category + month
    ),
    Question(
        "what will the weather be like next week",
        lambda s, a: a.kind in ("message", "clarify"),  # not in our data; must not invent
    ),

    # --- vague on its own, but has a sensible everyday reading ---
    Question("families in Moga", _is_table),
    Question("how many children are studying", _count_check(lambda s: s.execute(
        __import__("sqlalchemy").text(
            "SELECT count(*) FROM family_members m JOIN families f ON f.id = m.family_id "
            "WHERE NOT f.is_draft AND m.relation IN ('son', 'daughter') AND m.is_studying = true"
        )
    ).scalar())),

    # --- misspelling tolerance ---
    Question("families in Mogaa", lambda s, a: a.kind == "table"),  # typo in district
]


def _cea_count(session, year_label: str | None) -> int:
    scheme = ensure_cea_scheme(session)
    session.commit()
    year = (
        AcademicYear.parse(year_label, scheme.rules.get("academic_year_start_month", 4))
        if year_label
        else AcademicYear.last_completed(TODAY, scheme.rules.get("academic_year_start_month", 4))
    )
    from sqlalchemy.orm import selectinload

    families = session.scalars(
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.members), selectinload(Family.soldier))
    ).all()
    return sum(
        len(evaluate_family(f, year, scheme.rules).eligible_children) for f in families
    )


def _cea_count_current(session) -> int:
    """Children eligible for the academic year running right now (one ahead
    of the last-completed year the CEA tool defaults to)."""
    last = AcademicYear.last_completed(TODAY)
    return _cea_count(session, AcademicYear(last.start_year + 1, last.start_month).label)


def run_followups(session) -> list[tuple[Question, bool]]:
    """Two-question chains, checked separately because they need history."""
    from app.services.ask import Turn

    results = []
    first = answer_question(session, "how many widow names start with A")
    history = [Turn(question="how many widow names start with A", title=first.title, sql=first.sql)]
    second = answer_question(session, "list them", history)
    want = session.scalar(
        select(func.count()).select_from(Family)
        .where(Family.is_draft.is_(False), Family.primary_contact_name.ilike("A%"))
    )
    # "how many" may come back as the number or (fairly) as the list itself.
    first_count = first.rows[0][0] if len(first.columns) == 1 and first.rows else first.count
    ok = (
        first.kind == "table"
        and second.kind == "table"
        and first_count == want
        and second.count == want
    )
    results.append((Question("[follow-up] how many widow names start with A -> list them",
                              lambda s, a: True), ok))

    # The colonel's own chat: a CEA check for one widow, then "how about X?".
    first = answer_question(session, "is meena dagar eligible for cea")
    history = [Turn(question="is meena dagar eligible for cea", title=first.title, tool=first.tool)]
    second = answer_question(session, "how about sunanda pawar?", history)
    ok = (
        first.kind == "table" and "Meena Dagar" in first.title
        and second.kind == "table" and "Sunanda Pawar" in second.title
        and (second.tool or "").startswith("cea")
    )
    results.append((Question("[follow-up] is meena dagar eligible for cea -> how about sunanda pawar?",
                              lambda s, a: True), ok))

    # "how about X?" after a children question repeats the children question.
    first = answer_question(session, "how many kids does meena dagar have?")
    history = [Turn(question="how many kids does meena dagar have?", title=first.title, sql=first.sql)]
    second = answer_question(session, "how about sunanda pawar?", history)
    ok = second.kind == "table" and not (second.tool or "").startswith("cea")
    results.append((Question("[follow-up] how many kids does meena dagar have? -> how about sunanda pawar?",
                              lambda s, a: True), ok))
    return results


def main() -> int:
    if settings.llm_provider.lower() != "gemini":
        print("Set LLM_PROVIDER=gemini in .env before running this script.")
        return 1

    session = SessionLocal()
    passed = 0
    failed: list[str] = []

    for q in QUESTIONS:
        answer = answer_question(session, q.text)
        ok = q.check(session, answer)
        passed += ok
        mark = "PASS" if ok else "FAIL"
        shown = answer.title or answer.message or answer.error or ""
        print(f"[{mark}] {q.text!r} -> {answer.kind} | {shown[:80]}")
        if not ok:
            failed.append(q.text)

    for q, ok in run_followups(session):
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q.text}")
        if not ok:
            failed.append(q.text)

    total = len(QUESTIONS) + 3
    print(f"\n{passed}/{total} correct")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f}")
    session.close()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
