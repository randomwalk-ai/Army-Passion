"""Decide whether a row from the sheet is someone we already have.

This never merges anything. It reports what it found and how sure it is; an
officer decides. How to merge duplicates is still an open question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
        positions = sorted(
            {p for word in row_widow | row_soldier for p in self._by_word.get(word, ())}
        )

        for position in positions:
            family = self.families[position]
            soldier = family.soldier

            widow_score = _overlap(row_widow, self._widow_words[position])
            soldier_score = _overlap(row_soldier, self._soldier_words[position]) if soldier else 0
            if widow_score < 0.6 and soldier_score < 0.6:
                continue

            if widow_score >= 0.99:
                add(family, 30, "Widow's name is the same")
            elif widow_score >= 0.6:
                add(family, 18, "Widow's name is very close")

            if soldier_score >= 0.99:
                add(family, 30, "Soldier's name is the same")
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
