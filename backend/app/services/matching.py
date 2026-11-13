"""Decide whether a row from the sheet is someone we already have.

This never merges anything. It reports what it found and how sure it is; an
officer decides. How to merge duplicates is still an open question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Family, Soldier
from app.services.row_parser import ParsedRow


@dataclass
class Candidate:
    family_id: int
    family_code: str
    score: int  # 0-100
    reasons: list[str]


@dataclass
class MatchResult:
    best: Candidate | None
    others: list[Candidate]

    @property
    def is_confident(self) -> bool:
        """Sure enough to treat the row as an update rather than a new family."""
        return self.best is not None and self.best.score >= 80

    @property
    def is_uncertain(self) -> bool:
        """Close enough to be worth asking about, not close enough to act on.

        The floor is 40 because "same widow's name, same district" scores 45,
        and in this data that is a real duplicate signal — worth an officer
        glancing at, never worth merging on.
        """
        return self.best is not None and 40 <= self.best.score < 80


def simplify(text: str | None) -> str:
    """'Sunita  Devi' and 'SUNITA DEVI' become the same thing."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def name_similarity(a: str | None, b: str | None) -> float:
    """Share of word-parts the two names have in common."""
    first, second = set(simplify(a).split()), set(simplify(b).split())
    if not first or not second:
        return 0.0
    return len(first & second) / max(len(first), len(second))


def _overlap(first: set[str], second: set[str]) -> float:
    """name_similarity for names already split into words."""
    if not first or not second:
        return 0.0
    return len(first & second) / max(len(first), len(second))


def sound_key(word: str) -> str:
    """How a name sounds, roughly, so Indian spelling variants line up.

    Keep the first letter, drop the other vowels and h/w/y, merge doubled
    letters: Sunita / Suneeta -> "snt", Gurpreet / Gurprit -> "grprt",
    Kaur / Kour -> "kr", Mohinder / Mahinder -> "mndr".
    """
    if not word:
        return ""
    rest = re.sub(r"[aeiouhwy]", "", word[1:])
    key = word[0] + rest
    return re.sub(r"(.)+", r"", key)


def words_close(a: str, b: str) -> bool:
    """Same word, or the same word spelt a little differently."""
    if a == b:
        return True
    if len(a) < 3 or len(b) < 3 or a[0] != b[0]:
        return False
    return sound_key(a) == sound_key(b) or SequenceMatcher(None, a, b).ratio() >= 0.85


def _fuzzy_overlap(first: set[str], second: set[str]) -> float:
    """Like _overlap, but a word spelt slightly differently still counts."""
    if not first or not second:
        return 0.0
    close = sum(1 for word in first if any(words_close(word, other) for other in second))
    return close / max(len(first), len(second))


class FamilyIndex:
    """Loads the families once, so matching 60 rows does not mean 60 queries."""

    def __init__(self, session: Session) -> None:
        # Children are loaded with the families (one trip, not one per family):
        # the preview compares them and the import updates them.
        self.families: list[Family] = list(
            session.scalars(
                select(Family).options(
                    selectinload(Family.soldier), selectinload(Family.members)
                )
            ).all()
        )
        self.by_service_number: dict[str, Family] = {}
        self.by_phone: dict[str, list[Family]] = {}
        # Names split into words once, here, instead of once per sheet row.
        self._widow_words: list[set[str]] = []
        self._soldier_words: list[set[str]] = []
        self._district: list[str] = []
        # word -> positions of the families whose widow or soldier name has it.
        # Two names can only be "close" if they share a word, so a row is only
        # compared with families that share one.
        self._by_word: dict[str, list[int]] = {}

        for position, family in enumerate(self.families):
            soldier: Soldier | None = family.soldier
            if soldier and soldier.service_number:
                self.by_service_number[simplify(soldier.service_number)] = family
            if family.primary_phone:
                digits = re.sub(r"[^\d]", "", family.primary_phone)[-10:]
                if digits:
                    self.by_phone.setdefault(digits, []).append(family)

            widow_words = set(simplify(family.primary_contact_name).split())
            soldier_words = set(simplify(soldier.full_name).split()) if soldier else set()
            self._widow_words.append(widow_words)
            self._soldier_words.append(soldier_words)
            self._district.append(simplify(family.district))
            for word in widow_words | soldier_words:
                self._by_word.setdefault(word, []).append(position)
                # Also by sound, so "Suneeta" finds "Sunita".
                self._by_word.setdefault(f"~{sound_key(word)}", []).append(position)

    def find(self, row: ParsedRow) -> MatchResult:
        scores: dict[int, Candidate] = {}

        def add(family: Family, points: int, reason: str) -> None:
            existing = scores.get(family.id)
            if existing is None:
                scores[family.id] = Candidate(
                    family_id=family.id,
                    family_code=family.family_code,
                    score=points,
                    reasons=[reason],
                )
            else:
                existing.score = min(100, existing.score + points)
                existing.reasons.append(reason)

        # 1. Service number is as close to an identifier as this data gets.
        service_number = row.values.get("service_number")
        if service_number:
            match = self.by_service_number.get(simplify(str(service_number)))
            if match:
                add(match, 85, f"Same service number ({service_number})")

        # 2. Phone number.
        phone = row.values.get("phone")
        if phone:
            digits = re.sub(r"[^\d]", "", str(phone))[-10:]
            for match in self.by_phone.get(digits, []):
                add(match, 45, "Same phone number")

        # 3. Names, place and date of death together.
        widow_name = row.values.get("widow_name")
        soldier_name = row.values.get("soldier_name")
        district = row.values.get("district")
        date_of_death = row.values.get("date_of_death")

        row_widow = set(simplify(widow_name).split()) if widow_name else set()
        row_soldier = set(simplify(soldier_name).split()) if soldier_name else set()
        row_district = simplify(district) if district else ""
        # Families sharing at least one word, in their original order (so ties
        # rank exactly as before).
        lookups = {w for w in row_widow | row_soldier} | {
            f"~{sound_key(w)}" for w in row_widow | row_soldier
        }
        positions = sorted({p for key in lookups for p in self._by_word.get(key, ())})

        for position in positions:
            family = self.families[position]
            soldier = family.soldier

            # Exact words decide "the same"; spelling-tolerant words decide "close".
            widow_exact = _overlap(row_widow, self._widow_words[position])
            soldier_exact = _overlap(row_soldier, self._soldier_words[position]) if soldier else 0
            widow_score = _fuzzy_overlap(row_widow, self._widow_words[position])
            soldier_score = (
                _fuzzy_overlap(row_soldier, self._soldier_words[position]) if soldier else 0
            )
            if widow_score < 0.6 and soldier_score < 0.6:
                continue

            if widow_exact >= 0.99:
                add(family, 30, "Widow's name is the same")
            elif widow_score >= 0.99:
                add(family, 24, "Widow's name is spelt slightly differently")
            elif widow_score >= 0.6:
                add(family, 18, "Widow's name is very close")

            if soldier_exact >= 0.99:
                add(family, 30, "Soldier's name is the same")
            elif soldier_score >= 0.99:
                add(family, 24, "Soldier's name is spelt slightly differently")
            elif soldier_score >= 0.6:
                add(family, 18, "Soldier's name is very close")

            if row_district and row_district == self._district[position]:
                add(family, 15, f"Same district ({district})")

            if (
                date_of_death
                and soldier
                and soldier.date_of_death
                and date_of_death == soldier.date_of_death
            ):
                add(family, 25, "Same date of death")

        ranked = sorted(scores.values(), key=lambda c: c.score, reverse=True)
        if not ranked:
            return MatchResult(best=None, others=[])
        return MatchResult(best=ranked[0], others=ranked[1:3])


def signature_for_duplicate_check(row: ParsedRow) -> str | None:
    """A fingerprint used to spot two rows in the SAME sheet being the same person."""
    widow = simplify(str(row.values.get("widow_name") or ""))
    soldier = simplify(str(row.values.get("soldier_name") or ""))
    service = simplify(str(row.values.get("service_number") or ""))
    if service:
        return f"sn:{service}"
    if widow or soldier:
        district = simplify(str(row.values.get("district") or ""))
        return f"nm:{widow}|{soldier}|{district}"
    return None


# --- the same family twice in one sheet ----------------------------------------


@dataclass
class RowFacts:
    """The details of one sheet row that tell families apart, ready to compare."""

    position: int
    service: str
    phone: str
    widow: set[str]
    soldier: set[str]
    district: str
    date_of_death: object


def facts_of(position: int, row: ParsedRow) -> RowFacts:
    values = row.values
    return RowFacts(
        position=position,
        service=simplify(str(values.get("service_number") or "")),
        phone=re.sub(r"[^\d]", "", str(values.get("phone") or ""))[-10:],
        widow=set(simplify(str(values.get("widow_name") or "")).split()),
        soldier=set(simplify(str(values.get("soldier_name") or "")).split()),
        district=simplify(str(values.get("district") or "")),
        date_of_death=values.get("date_of_death"),
    )


def score_rows(a: RowFacts, b: RowFacts) -> tuple[int, list[str]]:
    """How alike two sheet rows are, with the same points as FamilyIndex.find."""
    score, reasons = 0, []
    if a.service and a.service == b.service:
        score, reasons = score + 85, reasons + ["Same service number"]
    if a.phone and a.phone == b.phone:
        score, reasons = score + 45, reasons + ["Same phone number"]

    widow = _fuzzy_overlap(a.widow, b.widow)
    soldier = _fuzzy_overlap(a.soldier, b.soldier)
    if widow >= 0.6 or soldier >= 0.6:
        for label, exact, close in (
            ("Widow's name", _overlap(a.widow, b.widow), widow),
            ("Soldier's name", _overlap(a.soldier, b.soldier), soldier),
        ):
            if exact >= 0.99:
                score, reasons = score + 30, reasons + [f"{label} is the same"]
            elif close >= 0.99:
                score, reasons = score + 24, reasons + [f"{label} is spelt slightly differently"]
            elif close >= 0.6:
                score, reasons = score + 18, reasons + [f"{label} is very close"]
        if a.district and a.district == b.district:
            score, reasons = score + 15, reasons + ["Same district"]
        if a.date_of_death and a.date_of_death == b.date_of_death:
            score, reasons = score + 25, reasons + ["Same date of death"]
    return min(100, score), reasons


class SheetIndex:
    """The rows of one sheet seen so far, so each new row is compared only with
    earlier rows that share a name (or a name that sounds the same), the army
    number or the phone — not with every row."""

    def __init__(self) -> None:
        self.rows: list[RowFacts] = []
        self._by_key: dict[str, list[int]] = {}

    def _keys(self, facts: RowFacts) -> set[str]:
        words = facts.widow | facts.soldier
        keys = {f"w:{w}" for w in words} | {f"~{sound_key(w)}" for w in words}
        if facts.service:
            keys.add(f"sn:{facts.service}")
        if facts.phone:
            keys.add(f"ph:{facts.phone}")
        return keys

    def add(self, facts: RowFacts) -> None:
        at = len(self.rows)
        self.rows.append(facts)
        for key in self._keys(facts):
            self._by_key.setdefault(key, []).append(at)

    def best(self, facts: RowFacts) -> tuple[RowFacts, int, list[str]] | None:
        """The earlier row most like this one, if any is alike at all."""
        found: tuple[RowFacts, int, list[str]] | None = None
        for at in sorted({i for key in self._keys(facts) for i in self._by_key.get(key, ())}):
            earlier = self.rows[at]
            score, reasons = score_rows(facts, earlier)
            if score and (found is None or score > found[1]):
                found = (earlier, score, reasons)
        return found
