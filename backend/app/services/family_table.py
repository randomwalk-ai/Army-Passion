"""The families as one big table he can read and correct, like his Excel sheet.

Every detail the database holds has a column, so nothing is hidden. Each
column says where its value lives (the family, the soldier, one of the
children, or the family's extra fields), how a typed value is checked, and
whether it can be edited at all. A correction goes through the same cleaners as the Excel
import, and every change is written to field history first, so nothing is
ever lost.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditLog, CustomField, Document, Family, FamilyMember, FieldHistory, Soldier
from app.models.enums import ChangeSource, DutyStatus, Language
from app.services import eligibility
from app.services.children import CHILD_RELATIONS, CHILD_SLOTS, SheetChild
from app.services.row_parser import (
    parse_amount,
    parse_cause,
    parse_date,
    parse_email,
    parse_geolocation,
    parse_ifsc,
    parse_phone,
    parse_pincode,
    parse_sex,
    tidy_name,
)

IST = ZoneInfo("Asia/Kolkata")
EXTRA = "extra."
SCHEME = "scheme."
PROFILE = "profile"


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


def _yes_no(raw: str) -> tuple[bool | None, str | None]:
    text = raw.strip().lower()
    if not text:
        return None, None
    if text in {"yes", "y", "true", "1"}:
        return True, None
    if text in {"no", "n", "false", "0"}:
        return False, None
    return None, f"'{raw}' is not Yes or No"


def _duty(raw: str) -> tuple[DutyStatus | None, str | None]:
    text = raw.strip().lower().replace(" ", "_")
    if not text:
        return None, None
    try:
        return DutyStatus(text), None
    except ValueError:
        return None, f"'{raw}' is not On duty, On leave or Unknown"


def _last4(raw: str) -> tuple[str | None, str | None]:
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None, None
    if len(digits) != 4:
        return None, "Type only the last 4 digits of the Aadhaar number"
    return digits, None


YES_NO = ("Yes", "No")


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    # "family" | "soldier" | "child" | "extra" | "computed"
    lives_on: str
    attr: str = ""
    # How the screen shows the editor: text, phone, date, number, choice
    # (and "status" for a scheme's eligibility, which is worked out, not typed).
    kind: str = "text"
    clean: Callable[[str], tuple[Any, str | None]] = _plain
    required: bool = False
    choices: tuple[str, ...] = ()
    # The heading it sits under in the family panel.
    group: str = "Next of kin"
    # Child 1, 2 or 3 (oldest first), for a child's column.
    slot: int = 0

    @property
    def editable(self) -> bool:
        return self.lives_on != "computed" and self.key != "family_code"

    @property
    def sortable(self) -> bool:
        return self.lives_on in ("family", "soldier") or self.key == PROFILE


LANGUAGES = tuple(language.value for language in Language)

# The order of his sheet: who to call first, then the soldier, where they
# live, the children, money, unit contact, CEA details, and anything else.
NOK, SOLDIER, ADDRESS, CHILDREN, BANK, UNIT, CEA, OTHER = (
    "Next of kin", "Soldier", "Address", "Children", "Pension and bank",
    "Unit contact", "CEA", "Other",
)


def _child_columns(slot: int) -> list[Column]:
    def child(key: str, label: str, attr: str, **more: Any) -> Column:
        return Column(f"child{slot}_{key}", f"Child {slot} {label}", "child", attr,
                      group=f"Child {slot}", slot=slot, **more)

    return [
        child("name", "name", "full_name", clean=_name),
        child("sex", "sex", "gender", kind="choice", clean=parse_sex, choices=("male", "female")),
        child("dob", "date of birth", "date_of_birth", kind="date", clean=parse_date),
        child("marital_status", "marital status", "marital_status"),
        child("is_studying", "studying?", "is_studying", kind="choice", clean=_yes_no,
              choices=YES_NO),
        child("education_level", "education level", "education_level"),
        child("current_class", "class", "current_class"),
        child("section", "section", "section"),
        child("roll_number", "roll no.", "roll_number"),
        child("admission_number", "admission no.", "admission_number"),
        child("academic_year", "academic year", "academic_year"),
        child("school_name", "school name", "school_name"),
        child("school_place", "school place", "school_place"),
        child("school_type", "school type", "school_type"),
        child("school_board", "board", "school_board"),
        child("school_affiliation_code", "affiliation code", "school_affiliation_code"),
        child("is_hostel", "in hostel?", "is_hostel", kind="choice", clean=_yes_no,
              choices=YES_NO),
        child("is_employed", "employed?", "is_employed", kind="choice", clean=_yes_no,
              choices=YES_NO),
        child("has_disability", "disability?", "has_disability", kind="choice", required=True,
              clean=_yes_no, choices=YES_NO),
        child("aadhaar_last4", "Aadhaar last 4", "aadhaar_last4", kind="number", clean=_last4),
    ]


COLUMNS: list[Column] = [
    Column("primary_contact_name", "Next of kin", "family", "primary_contact_name",
           clean=_name, required=True),
    Column(PROFILE, "Profile", "computed", kind="profile"),
    Column("family_code", "Family code", "family", "family_code"),
    Column("nok_relationship", "Relation", "family", "nok_relationship"),
    Column("primary_phone", "Mobile", "family", "primary_phone", kind="phone", clean=parse_phone),
    Column("alternate_phone", "Other phone", "family", "alternate_phone", kind="phone",
           clean=parse_phone),
    Column("email", "Email", "family", "email", clean=parse_email),
    Column("preferred_language", "Language", "family", "preferred_language", kind="choice",
           clean=_language, required=True, choices=LANGUAGES),
    Column("whatsapp_opted_in", "WhatsApp OK?", "family", "whatsapp_opted_in", kind="choice",
           clean=_yes_no, required=True, choices=YES_NO),
    Column("nok_is_govt_servant", "Govt servant?", "family", "nok_is_govt_servant",
           kind="choice", clean=_yes_no, choices=YES_NO),
    Column("last_contacted_on", "Last contacted", "family", "last_contacted_on", kind="date",
           clean=parse_date),
    Column("last_verified_on", "Last verified", "family", "last_verified_on", kind="date",
           clean=parse_date),
    Column("documents", "Documents", "computed"),
    Column("soldier_name", "Soldier", "soldier", "full_name", clean=_name, required=True,
           group=SOLDIER),
    Column("soldier_rank", "Rank", "soldier", "rank", group=SOLDIER),
    Column("service_number", "Army no.", "soldier", "service_number", clean=_upper,
           group=SOLDIER),
    Column("unit", "Serving unit", "soldier", "unit", group=SOLDIER),
    Column("regiment", "Parent unit", "soldier", "regiment", group=SOLDIER),
    Column("soldier_dob", "Soldier's date of birth", "soldier", "date_of_birth", kind="date",
           clean=parse_date, group=SOLDIER),
    Column("date_of_enrolment", "Date of enrolment", "soldier", "date_of_enrolment",
           kind="date", clean=parse_date, group=SOLDIER),
    Column("date_of_death", "Date of death", "soldier", "date_of_death", kind="date",
           clean=parse_date, group=SOLDIER),
    Column("cause_of_death", "Cause of death", "soldier", "cause_sub_category", group=SOLDIER),
    Column("place_of_death", "Place of death", "soldier", "place_of_death", group=SOLDIER),
    Column("district_of_death", "District of death", "soldier", "district_of_death",
           group=SOLDIER),
    Column("state_of_death", "State of death", "soldier", "state_of_death", group=SOLDIER),
    Column("weather_at_death", "Weather at death", "soldier", "weather_at_death",
           group=SOLDIER),
    Column("duty_status", "On duty or leave", "soldier", "duty_status", kind="choice",
           clean=_duty, required=True, choices=("on duty", "on leave", "unknown"),
           group=SOLDIER),
    Column("address_line", "Full address", "family", "address_line", group=ADDRESS),
    Column("village_or_town", "Village", "family", "village_or_town", group=ADDRESS),
    Column("town", "Town", "family", "town", group=ADDRESS),
    Column("tehsil", "Tehsil", "family", "tehsil", group=ADDRESS),
    Column("post_office", "Post office", "family", "post_office", group=ADDRESS),
    Column("district", "District", "family", "district", group=ADDRESS),
    Column("state", "State", "family", "state", group=ADDRESS),
    Column("pincode", "PIN code", "family", "pincode", kind="number", clean=parse_pincode,
           group=ADDRESS),
    Column("gps_coordinates", "GPS location", "family", "gps_coordinates",
           clean=parse_geolocation, group=ADDRESS),
    Column("children", "Number of children", "computed", group=CHILDREN),
    *(column for slot in CHILD_SLOTS for column in _child_columns(slot)),
    Column("ppo_number", "PPO no.", "family", "ppo_number", clean=_upper, group=BANK),
    Column("bank_name", "Bank", "family", "bank_name", group=BANK),
    Column("bank_branch", "Branch", "family", "bank_branch", group=BANK),
    Column("bank_account_number", "Account no.", "family", "bank_account_number",
           kind="number", clean=_upper, group=BANK),
    Column("bank_ifsc", "IFSC", "family", "bank_ifsc", clean=parse_ifsc, group=BANK),
    Column("bank_account_holder", "Account holder", "family", "bank_account_holder",
           clean=_name, group=BANK),
    Column("bank_address", "Bank address", "family", "bank_address", group=BANK),
    Column("co_unit_name", "CO unit name", "family", "co_unit_name", group=UNIT),
    Column("co_unit_phone", "CO unit phone", "family", "co_unit_phone", kind="phone",
           clean=parse_phone, group=UNIT),
    Column("record_office", "Record office", "family", "record_office", group=CEA),
    Column("correspondence_address", "Correspondence address", "family",
           "correspondence_address", group=CEA),
    Column("correspondence_pincode", "Correspondence PIN", "family", "correspondence_pincode",
           kind="number", clean=parse_pincode, group=CEA),
    Column("annual_income", "Annual income (₹)", "family", "annual_income", kind="number",
           clean=parse_amount, group=OTHER),
    Column("monthly_pension_amount", "Monthly pension (₹)", "family", "monthly_pension_amount",
           kind="number", clean=parse_amount, group=OTHER),
    Column("notes", "Notes", "family", "notes", group=OTHER),
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
        Column(f"{SCHEME}{s.code}", s.short_name, "computed", s.code, kind="status",
               group="What they can claim")
        for s in eligibility.SCHEMES
    ]
    at = next(i for i, c in enumerate(COLUMNS) if c.key == "documents") + 1
    return (
        COLUMNS[:at] + schemes + COLUMNS[at:]
        + [Column(f"{EXTRA}{f.key}", f.label, "extra", f.key, group="Extra fields")
           for f in extras]
    )


def _show(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return str(value.value).replace("_", " ")
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return text or None


def children_of(family: Family) -> list[FamilyMember]:
    """Child 1, 2, 3...: the oldest first; children without a birth date last."""
    kids = [m for m in family.members if m.relation in CHILD_RELATIONS]
    return sorted(
        kids, key=lambda m: (m.date_of_birth is None, m.date_of_birth or date.max, m.id or 0)
    )


def _child(column: Column, family: Family) -> FamilyMember | None:
    kids = children_of(family)
    return kids[column.slot - 1] if column.slot <= len(kids) else None


def _read(column: Column, family: Family) -> Any:
    if column.lives_on == "family":
        return getattr(family, column.attr)
    if column.lives_on == "soldier":
        soldier = family.soldier
        if soldier is None:
            return None
        if column.key == "cause_of_death":
            # His own words if we have them, else the category it was filed under.
            if soldier.cause_sub_category or not soldier.cause_category:
                return soldier.cause_sub_category
            return soldier.cause_category.value.replace("_", " ").capitalize()
        return getattr(soldier, column.attr)
    if column.lives_on == "child":
        child = _child(column, family)
        return getattr(child, column.attr) if child else None
    if column.lives_on == "extra":
        return (family.extra_fields or {}).get(column.attr)
    return None


def completeness(family: Family, cols: list[Column], documents: int) -> tuple[int, list[str]]:
    """How much of the profile is filled in (0-100) and the labels still empty.

    Every detail counts, except a child's details for a child who doesn't
    exist (a family with one child is not marked down for Child 2 and 3) and
    the scheme answers, which are worked out rather than typed. Rounded down,
    so 100% always means nothing at all is missing.
    """
    kids = len(children_of(family))
    missing: list[str] = []
    counted = 0
    for column in cols:
        if column.kind in ("status", "profile"):
            continue
        if column.lives_on == "child" and column.slot > kids:
            continue
        counted += 1
        if column.key == "documents":
            filled = documents > 0
        elif column.key == "children":
            filled = kids > 0
        else:
            filled = _show(_read(column, family)) is not None
        if not filled:
            missing.append(column.label)
    if not counted:
        return 100, []
    return (counted - len(missing)) * 100 // counted, missing


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
    values["children"] = len(children_of(family))
    percent, missing = completeness(family, cols, documents)
    values[PROFILE] = percent
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
    return {
        "family_id": family.id,
        "values": values,
        "eligibility": schemes,
        "missing": missing,
    }


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

    total = counts.get(filter_key, counts["all"])
    page_size = max(1, min(page_size, 100))
    last_page = max(1, -(-total // page_size))
    page_number = max(1, min(page_number, last_page))
    loaded = statement.options(selectinload(Family.soldier), selectinload(Family.members))

    if sort == PROFILE:
        # Worked out in Python across every matching family (a few thousand at
        # most), then one page cut out, so the order is right across pages.
        everyone = session.scalars(loaded.order_by(Family.primary_contact_name, Family.id)).all()
        documents = supporting_counts(session, [f.id for f in everyone])
        scored = sorted(
            everyone,
            key=lambda f: completeness(f, cols, documents.get(f.id, 0))[0],
            reverse=descending,
        )
        start = (page_number - 1) * page_size
        families = scored[start:start + page_size]
    else:
        by = next((c for c in cols if c.key == sort and c.sortable and c.key != PROFILE), cols[0])
        target = getattr(Family if by.lives_on == "family" else Soldier, by.attr)
        order = target.desc().nulls_last() if descending else target.asc().nulls_last()
        families = session.scalars(
            loaded.order_by(order, Family.id)
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

    if column.lives_on == "child":
        return _edit_child(session, family, column, old, new, user_id)

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
        if column.key == "cause_of_death":
            entity.cause_category = parse_cause(new)[0] if new else None
        elif column.key == "gps_coordinates":
            from app.services.import_apply import point_from_gps

            family.location = point_from_gps(new)

    _audit(session, family, key, user_id, now)
    return True


def _audit(session: Session, family: Family, key: str, user_id: int | None, now: datetime) -> None:
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


def _edit_child(
    session: Session, family: Family, column: Column, old: Any, new: Any, user_id: int | None
) -> bool:
    """Change Child 1, 2 or 3. A name typed into an empty child adds that child."""
    child = _child(column, family)
    now = datetime.now(IST)
    if child is None:
        count = len(children_of(family))
        if column.attr != "full_name":
            raise CellProblem(f"Type Child {column.slot}'s name first.")
        if column.slot > count + 1:
            raise CellProblem(f"Add Child {count + 1} first.")
        child = FamilyMember(full_name=new, relation=SheetChild(column.slot, new, None, None, None).relation)
        family.members.append(child)
        session.flush()
        _child_history(session, child, "__created__", None, new, user_id, now)
        _audit(session, family, column.key, user_id, now)
        return True

    if column.attr == "full_name" and new is None:
        raise CellProblem("A child's name cannot be left empty.")
    _child_history(session, child, column.attr, _show(old), _show(new), user_id, now)
    setattr(child, column.attr, new)
    # Keep the son/daughter and married flags in step with what he typed.
    facts = SheetChild(column.slot, child.full_name, child.gender, None, child.marital_status)
    if column.attr == "gender":
        child.relation = facts.relation
    elif column.attr == "marital_status":
        child.is_married = facts.is_married
    _audit(session, family, column.key, user_id, now)
    return True


def _child_history(
    session: Session, child: FamilyMember, field_name: str, old: Any, new: Any,
    user_id: int | None, now: datetime,
) -> None:
    session.add(
        FieldHistory(
            entity_type="family_member",
            entity_id=child.id,
            field_name=field_name,
            old_value=old,
            new_value=new,
            source=ChangeSource.officer_entry,
            source_reference="Families table",
            changed_at=now,
            changed_by_user_id=user_id,
            note="Edited in the families table",
        )
    )


def profile_spread(session: Session) -> dict[str, Any]:
    """How many families sit at each profile percentage (0 to 100), with the
    average and the spread (standard deviation) that the bell curve is drawn from."""
    cols = columns(session)
    families = session.scalars(
        select(Family)
        .where(Family.is_draft.is_(False))
        .options(selectinload(Family.soldier), selectinload(Family.members))
    ).all()
    documents = supporting_counts(session, [f.id for f in families])
    counts = [0] * 101
    for family in families:
        counts[completeness(family, cols, documents.get(family.id, 0))[0]] += 1
    total = len(families)
    if not total:
        return {"counts": counts, "total": 0, "average": 0.0, "spread": 0.0}
    average = sum(p * n for p, n in enumerate(counts)) / total
    spread = (sum(n * (p - average) ** 2 for p, n in enumerate(counts)) / total) ** 0.5
    return {
        "counts": counts,
        "total": total,
        "average": round(average, 1),
        "spread": round(spread, 1),
    }
