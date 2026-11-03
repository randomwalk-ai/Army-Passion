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


class FamilyIndex:
    """Loads the families once, so matching 60 rows does not mean 60 queries."""

    def __init__(self, session: Session) -> None:
        self.families: list[Family] = list(
            session.scalars(
                select(Family).options(selectinload(Family.soldier))
            ).all()
        )
        self.by_service_number: dict[str, Family] = {}
        self.by_phone: dict[str, list[Family]] = {}

        for family in self.families:
            soldier: Soldier | None = family.soldier
            if soldier and soldier.service_number:
                self.by_service_number[simplify(soldier.service_number)] = family
            if family.primary_phone:
                digits = re.sub(r"[^\d]", "", family.primary_phone)[-10:]
                if digits:
                    self.by_phone.setdefault(digits, []).append(family)

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

        for family in self.families:
            soldier = family.soldier

            widow_score = name_similarity(widow_name, family.primary_contact_name) if widow_name else 0
            soldier_score = (
                name_similarity(soldier_name, soldier.full_name)
                if soldier_name and soldier
                else 0
            )
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

            if district and simplify(district) == simplify(family.district):
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
