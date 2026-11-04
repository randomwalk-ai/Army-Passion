"""The families as one big table he can read and correct, like his Excel sheet.

Each column says where its value lives (the family, the soldier, or the
family's extra fields), how a typed value is checked, and whether it can be
edited at all. A correction goes through the same cleaners as the Excel
import, and every change is written to field history first, so nothing is
ever lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditLog, CustomField, Document, Family, FieldHistory, Soldier
from app.models.enums import ChangeSource, Language, Relation
from app.services import eligibility
from app.services.row_parser import (
    parse_date,
    parse_email,
    parse_ifsc,
    parse_phone,
    parse_pincode,
    tidy_name,
)

IST = ZoneInfo("Asia/Kolkata")
EXTRA = "extra."
SCHEME = "scheme."
CHILD_RELATIONS = (Relation.son, Relation.daughter)


class CellProblem(ValueError):
    """A typed value that cannot be stored as it is."""


def _plain(raw: str) -> tuple[str | None, str | None]:
    text = " ".join(raw.split())
    return (text or None), None


def _name(raw: str) -> tuple[str | None, str | None]:
    return tidy_name(raw), None


def _upper(raw: str) -> tuple[str | None, str | None]:
    text = "".join(raw.split()).upper()
    return (text or None), None


def _language(raw: str) -> tuple[Language | None, str | None]:
    text = raw.strip().lower()
    if not text:
        return None, None
    try:
        return Language(text), None
    except ValueError:
        return None, f"'{raw}' is not one of the languages listed"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    # "family" | "soldier" | "extra" | "computed"
    lives_on: str
    attr: str = ""
    # How the screen shows the editor: text, phone, date, number, choice
    # (and "status" for a scheme's eligibility, which is worked out, not typed).
    kind: str = "text"
    clean: Callable[[str], tuple[Any, str | None]] = _plain
    required: bool = False
    choices: tuple[str, ...] = ()

    @property
    def editable(self) -> bool:
        return self.lives_on != "computed" and self.key != "family_code"

    @property
    def sortable(self) -> bool:
        return self.lives_on in ("family", "soldier")


LANGUAGES = tuple(language.value for language in Language)

# The order of his sheet: who to call first, then the soldier, then where they live.
COLUMNS: list[Column] = [
    Column("primary_contact_name", "Next of kin", "family", "primary_contact_name",
           clean=_name, required=True),
    Column("family_code", "Family code", "family", "family_code"),
    Column("nok_relationship", "Relation", "family", "nok_relationship"),
    Column("primary_phone", "Mobile", "family", "primary_phone", kind="phone", clean=parse_phone),
    Column("alternate_phone", "Other phone", "family", "alternate_phone", kind="phone",
           clean=parse_phone),
    Column("documents", "Documents", "computed"),
    Column("children", "Children", "computed"),
    Column("soldier_name", "Soldier", "soldier", "full_name", clean=_name, required=True),
    Column("soldier_rank", "Rank", "soldier", "rank"),
    Column("service_number", "Service no.", "soldier", "service_number", clean=_upper),
    Column("unit", "Unit", "soldier", "unit"),
    Column("date_of_death", "Date of death", "soldier", "date_of_death", kind="date",
           clean=parse_date),
    Column("village_or_town", "Village", "family", "village_or_town"),
    Column("district", "District", "family", "district"),
    Column("state", "State", "family", "state"),
    Column("pincode", "PIN code", "family", "pincode", kind="number", clean=parse_pincode),
    Column("preferred_language", "Language", "family", "preferred_language", kind="choice",
           clean=_language, required=True, choices=LANGUAGES),
    Column("ppo_number", "PPO no.", "family", "ppo_number", clean=_upper),
    Column("bank_name", "Bank", "family", "bank_name"),
    Column("bank_account_number", "Account no.", "family", "bank_account_number",
           kind="number", clean=_upper),
    Column("bank_ifsc", "IFSC", "family", "bank_ifsc", clean=parse_ifsc),
    Column("email", "Email", "family", "email", clean=parse_email),
]

FILTERS = {
    "all": "Everyone",
    "no_documents": "No documents yet",
    "no_phone": "No mobile number",
}


def columns(session: Session) -> list[Column]:
    """The fixed columns with one per scheme after Documents, then any extra
    fields he has approved from his sheets."""
    extras = session.scalars(
        select(CustomField).where(CustomField.is_active.is_(True)).order_by(CustomField.label)
    ).all()
    schemes = [
        Column(f"{SCHEME}{s.code}", s.short_name, "computed", s.code, kind="status")
        for s in eligibility.SCHEMES
    ]
    at = next(i for i, c in enumerate(COLUMNS) if c.key == "documents") + 1
    return (
        COLUMNS[:at] + schemes + COLUMNS[at:]
        + [Column(f"{EXTRA}{f.key}", f.label, "extra", f.key) for f in extras]
    )


def _show(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Language):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return text or None


def _read(column: Column, family: Family) -> Any:
    if column.lives_on == "family":
        return getattr(family, column.attr)
    if column.lives_on == "soldier":
        return getattr(family.soldier, column.attr) if family.soldier else None
    if column.lives_on == "extra":
        return (family.extra_fields or {}).get(column.attr)
    return None


@dataclass
class Page:
    columns: list[Column]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    counts: dict[str, int] = field(default_factory=dict)


def supporting_counts(session: Session, family_ids: list[int]) -> dict[int, int]:
    if not family_ids:
        return {}
    return dict(
        session.execute(
            select(Document.family_id, func.count())
            .where(Document.family_id.in_(family_ids), Document.is_supporting.is_(True))
            .group_by(Document.family_id)
        ).all()
    )


def row(
    family: Family,
    cols: list[Column],
    documents: int,
    verdicts: dict[str, eligibility.Verdict] | None = None,
) -> dict[str, Any]:
    values = {c.key: _show(_read(c, family)) for c in cols if c.lives_on != "computed"}
    values["documents"] = documents
    values["children"] = sum(1 for m in family.members if m.relation in CHILD_RELATIONS)
    schemes = {}
    for code, verdict in (verdicts or {}).items():
        values[f"{SCHEME}{code}"] = verdict.status
        scheme = eligibility.by_code(code)
        schemes[code] = {
            "status": verdict.status,
            "label": scheme.status_labels[verdict.status] if scheme else verdict.status,
            "headline": verdict.headline,
            "amount": verdict.amount,
        }
    return {"family_id": family.id, "values": values, "eligibility": schemes}


def rows(session: Session, families: list[Family], cols: list[Column]) -> list[dict[str, Any]]:
    """Table rows with their document counts and every scheme's verdict."""
    documents = supporting_counts(session, [f.id for f in families])
    checked = eligibility.check_all(session, families)
    return [
        row(f, cols, documents.get(f.id, 0), {code: v[f.id] for code, v in checked.items()})
        for f in families
    ]


def page(
    session: Session,
    *,
    query: str = "",
    filter_key: str = "all",
    sort: str = "primary_contact_name",
    descending: bool = False,
    page_number: int = 1,
    page_size: int = 25,
) -> Page:
    cols = columns(session)
    has_documents = (
        select(Document.id)
        .where(Document.family_id == Family.id, Document.is_supporting.is_(True))
        .exists()
    )
    base = select(Family).outerjoin(Soldier, Family.soldier_id == Soldier.id).where(
        Family.is_draft.is_(False)
    )

    term = query.strip()
    if term:
        like = f"%{term}%"
        base = base.where(
            or_(
                Family.primary_contact_name.ilike(like),
                Family.family_code.ilike(like),
                Family.district.ilike(like),
                Family.state.ilike(like),
                Family.village_or_town.ilike(like),
                Family.primary_phone.ilike(like),
                Soldier.full_name.ilike(like),
                Soldier.service_number.ilike(like),
            )
        )

    # How many fall under each filter, for the numbers on the filter buttons.
    counts = {
        "all": session.scalar(select(func.count()).select_from(base.subquery())) or 0,
        "no_documents": session.scalar(
            select(func.count()).select_from(base.where(~has_documents).subquery())
        ) or 0,
        "no_phone": session.scalar(
            select(func.count()).select_from(
                base.where(Family.primary_phone.is_(None)).subquery()
            )
        ) or 0,
    }

    statement = base
    if filter_key == "no_documents":
        statement = statement.where(~has_documents)
    elif filter_key == "no_phone":
        statement = statement.where(Family.primary_phone.is_(None))

    by = next((c for c in cols if c.key == sort and c.sortable), cols[0])
    target = getattr(Family if by.lives_on == "family" else Soldier, by.attr)
    order = target.desc().nulls_last() if descending else target.asc().nulls_last()

    total = counts.get(filter_key, counts["all"])
    page_size = max(1, min(page_size, 100))
    last_page = max(1, -(-total // page_size))
    page_number = max(1, min(page_number, last_page))

    families = session.scalars(
        statement.options(selectinload(Family.soldier), selectinload(Family.members))
        .order_by(order, Family.id)
        .offset((page_number - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        columns=cols,
        rows=rows(session, list(families), cols),
        total=total,
        page=page_number,
        page_size=page_size,
        counts=counts,
    )


def edit_cell(
    session: Session, family: Family, key: str, raw: str | None, user_id: int | None
) -> bool:
    """Store one corrected value. Returns False when nothing actually changed.

    Clearing a box is allowed (it is a deliberate act here, unlike a blank in an
    imported sheet), except for the few values a family cannot be without. The
    old value always stays in field history.
    """
    column = next((c for c in columns(session) if c.key == key), None)
    if column is None:
        raise CellProblem("That column does not exist.")
    if not column.editable:
        raise CellProblem(f"{column.label} cannot be changed here.")

    text = (raw or "").strip()
    if not text:
        if column.required:
            raise CellProblem(f"{column.label} cannot be left empty.")
        new: Any = None
    else:
        new, problem = column.clean(text)
        if problem:
            raise CellProblem(problem)
        if new is None and column.required:
            raise CellProblem(f"{column.label} cannot be left empty.")

    old = _read(column, family)
    if _show(old) == _show(new):
        return False

    if column.lives_on == "soldier":
        entity, entity_type, field_name = family.soldier, "soldier", column.attr
        if entity is None:
            raise CellProblem("This family has no soldier record to change.")
    elif column.lives_on == "extra":
        entity, entity_type, field_name = family, "family", f"{EXTRA}{column.attr}"
    else:
        entity, entity_type, field_name = family, "family", column.attr

    now = datetime.now(IST)
    session.add(
        FieldHistory(
            entity_type=entity_type,
            entity_id=entity.id,
            field_name=field_name,
            old_value=_show(old),
            new_value=_show(new),
            source=ChangeSource.officer_entry,
            source_reference="Families table",
            changed_at=now,
            changed_by_user_id=user_id,
            note="Edited in the families table",
        )
    )
    if column.lives_on == "extra":
        pocket = dict(family.extra_fields or {})
        if new is None:
            pocket.pop(column.attr, None)
        else:
            pocket[column.attr] = new
        family.extra_fields = pocket  # a new dict, so the change is noticed
    else:
        setattr(entity, column.attr, new)

    session.add(
        AuditLog(
            user_id=user_id,
            action="family.update",
            entity_type="family",
            entity_id=family.id,
            occurred_at=now,
            details={"field": key, "via": "families table"},
        )
    )
    return True
