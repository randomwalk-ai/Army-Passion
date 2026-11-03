"""The CEA claim pack: filled in from the database, edited, saved, printed.

Three jobs:
1. `build_form`  - pre-fill every blank on the claim from what we know
2. `save_form`   - the officer's edits go back into the family's record,
                   with the old value kept in history (never overwritten)
3. `render_pdf`  - write the values onto the official scanned pages

The official form is a scan, with no fillable boxes, so the text is placed by
position. Positions are in PDF points (A4 = 595 x 842, origin bottom-left).
They were measured off a grid laid over the scan.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import AuditLog, Family, FamilyMember, FieldHistory
from app.models.enums import ChangeSource, Relation
from app.services.cea import AcademicYear, FamilyVerdict, ELIGIBLE
from app.services.row_parser import parse_date, parse_phone

IST = ZoneInfo("Asia/Kolkata")
FORM_PDF = Path(__file__).resolve().parents[2] / "CEA-Application" / "CEA 2026.pdf"

# Pages of the official PDF (0-based). Pages 0-1 are the rules, not the claim.
COVER, BILL, BILL_2, DECLARATION, SCHOOL = 2, 3, 4, 5, 6


# --- the form ----------------------------------------------------------------


class CeaChildForm(BaseModel):
    member_id: int | None = None
    name: str = ""
    relation: str = ""  # son / daughter, for "Master" or "Kumari"
    date_of_birth: str = ""  # DD-MM-YYYY
    current_class: str = ""
    section: str = ""
    roll_number: str = ""
    admission_number: str = ""
    school_name: str = ""
    school_place: str = ""
    school_board: str = ""
    school_affiliation_code: str = ""
    is_hostel: bool = False
    has_disability: bool = False
    period_from: str = ""  # DD-MM-YYYY
    period_to: str = ""
    cea_amount: int = 0
    hostel_amount: int = 0

    @property
    def total(self) -> int:
        return (self.cea_amount or 0) + (self.hostel_amount or 0)


class CeaForm(BaseModel):
    family_id: int
    academic_year: str
    dated: str = ""
    nok_name: str = ""
    soldier_name: str = ""
    soldier_rank: str = ""
    service_number: str = ""
    unit: str = ""
    record_office: str = ""
    record_office_pincode: str = ""
    home_address: str = ""
    permanent_pincode: str = ""
    correspondence_address: str = ""
    correspondence_pincode: str = ""
    mobile: str = ""
    bank_account_holder: str = ""
    bank_name: str = ""
    bank_branch: str = ""
    bank_address: str = ""
    bank_account_number: str = ""
    bank_ifsc: str = ""
    school_state: str = ""  # "recognised by ... board (name of the state/UT)"
    nok_is_govt_servant: bool | None = None
    children: list[CeaChildForm] = Field(default_factory=list, max_length=2)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return str(value)


def compose_address(family: Family) -> str:
    """The home address as one block, from whatever parts we have."""
    if family.address_line:
        parts = [family.address_line]
    else:
        parts = [
            f"Vill {family.village_or_town}" if family.village_or_town else "",
            family.town or "",
            f"PO {family.post_office}" if family.post_office and "po" not in family.post_office.lower() else family.post_office or "",
            f"Teh {family.tehsil}" if family.tehsil else "",
        ]
    for extra in (family.district and f"Distt {family.district}", family.state):
        if extra and extra not in parts[0]:
            parts.append(extra)
    return ", ".join(p for p in parts if p)


def _pincode_in(text: str | None) -> str:
    found = re.findall(r"\b\d{6}\b", text or "")
    return found[-1] if found else ""


def build_form(
    family: Family, verdict: FamilyVerdict, year: AcademicYear, today: date
) -> CeaForm:
    soldier = family.soldier
    home = compose_address(family)

    # The eligible children; if none, the two eldest, so the form is never empty.
    picked = verdict.eligible_children or verdict.children[:2]
    members = {m.id: m for m in family.members}
    children: list[CeaChildForm] = []
    first_claim_month = year.starts_on
    if soldier and soldier.date_of_death:
        death_month = soldier.date_of_death.replace(day=1)
        first_claim_month = max(first_claim_month, death_month)

    for child in picked[:2]:
        member = members.get(child.member_id) if child.member_id else None
        if member is None:
            continue
        children.append(
            CeaChildForm(
                member_id=member.id,
                name=member.full_name,
                relation=member.relation.value,
                date_of_birth=_text(member.date_of_birth),
                current_class=member.current_class or member.education_level or "",
                section=member.section or "",
                roll_number=member.roll_number or "",
                admission_number=member.admission_number or "",
                school_name=member.school_name or "",
                school_place=member.school_place or "",
                school_board=member.school_board or "",
                school_affiliation_code=member.school_affiliation_code or "",
                is_hostel=bool(member.is_hostel),
                has_disability=bool(member.has_disability),
                period_from=_text(first_claim_month),
                period_to=_text(year.ends_on),
                cea_amount=child.cea_amount,
                hostel_amount=child.hostel_amount,
            )
        )

    return CeaForm(
        family_id=family.id,
        academic_year=year.label,
        dated=_text(today),
        nok_name=family.primary_contact_name or "",
        soldier_name=soldier.full_name if soldier else "",
        soldier_rank=(soldier.rank or "") if soldier else "",
        service_number=(soldier.service_number or "") if soldier else "",
        unit=((soldier.unit or soldier.regiment) or "") if soldier else "",
        record_office=family.record_office or "",
        record_office_pincode=_pincode_in(family.record_office),
        home_address=home,
        permanent_pincode=family.pincode or "",
        correspondence_address=family.correspondence_address or home,
        correspondence_pincode=family.correspondence_pincode or family.pincode or "",
        mobile=family.primary_phone or "",
        bank_account_holder=family.bank_account_holder or family.primary_contact_name or "",
        bank_name=family.bank_name or "",
        bank_branch=family.bank_branch or "",
        bank_address=family.bank_address or "",
        bank_account_number=family.bank_account_number or "",
        bank_ifsc=family.bank_ifsc or "",
        school_state=family.state or "",
        nok_is_govt_servant=family.nok_is_govt_servant,
        children=children,
    )


# Blanks worth pointing out before he prints. (label, how to read it)
REQUIRED: list[tuple[str, Callable[[CeaForm], Any]]] = [
    ("Name of NOK", lambda f: f.nok_name),
    ("Soldier's rank", lambda f: f.soldier_rank),
    ("Army number", lambda f: f.service_number),
    ("Unit", lambda f: f.unit),
    ("Record office", lambda f: f.record_office),
    ("PIN code (permanent address)", lambda f: f.permanent_pincode),
    ("Mobile number", lambda f: f.mobile),
    ("Bank name", lambda f: f.bank_name),
    ("Account number", lambda f: f.bank_account_number),
    ("IFSC code", lambda f: f.bank_ifsc),
]
CHILD_REQUIRED: list[tuple[str, str]] = [
    ("class", "current_class"),
    ("school name", "school_name"),
    ("school place", "school_place"),
]


def missing_fields(form: CeaForm) -> list[str]:
    missing = [label for label, read in REQUIRED if not str(read(form) or "").strip()]
    if not form.children:
        missing.append("A child to claim for")
    for child in form.children:
        first = child.name.split()[0] if child.name else "Child"
        for label, attr in CHILD_REQUIRED:
            if not str(getattr(child, attr) or "").strip():
                missing.append(f"{first}: {label}")
    return missing


# --- saving edits back --------------------------------------------------------

# form field -> family column. Names are not changed from here on purpose:
# a renamed widow should be a deliberate edit, not a side effect of a claim.
FAMILY_SAVE = {
    "record_office": "record_office",
    "permanent_pincode": "pincode",
    "correspondence_address": "correspondence_address",
    "correspondence_pincode": "correspondence_pincode",
    "mobile": "primary_phone",
    "bank_account_holder": "bank_account_holder",
    "bank_name": "bank_name",
    "bank_branch": "bank_branch",
    "bank_address": "bank_address",
    "bank_account_number": "bank_account_number",
    "bank_ifsc": "bank_ifsc",
    "nok_is_govt_servant": "nok_is_govt_servant",
}
SOLDIER_SAVE = {"soldier_rank": "rank", "service_number": "service_number", "unit": "unit"}
CHILD_SAVE = {
    "date_of_birth": "date_of_birth",
    "current_class": "current_class",
    "section": "section",
    "roll_number": "roll_number",
    "admission_number": "admission_number",
    "school_name": "school_name",
    "school_place": "school_place",
    "school_board": "school_board",
    "school_affiliation_code": "school_affiliation_code",
    "is_hostel": "is_hostel",
}


class FormProblem(ValueError):
    """A value on the form that cannot be stored as typed."""

    def __init__(self, problems: dict[str, str]):
        super().__init__("; ".join(problems.values()))
        self.problems = problems


def _clean(field: str, value: Any) -> Any:
    """Store values the same way the Excel import does."""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if field == "mobile" and value:
        phone, problem = parse_phone(value)
        if problem:
            raise FormProblem({field: f"Mobile number: {problem}"})
        return phone
    if field == "date_of_birth" and value:
        parsed, problem = parse_date(value)
        if problem:
            raise FormProblem({field: f"Date of birth: {problem}"})
        return parsed
    if field == "bank_ifsc" and value:
        return value.upper()
    return value


def _same(old: Any, new: Any) -> bool:
    return _text(old).strip().lower() == _text(new).strip().lower()


def save_form(
    session: Session,
    family: Family,
    form: CeaForm,
    original: CeaForm,
    user_id: int | None,
) -> list[str]:
    """Write what he changed into the record. Returns what changed, in words.

    `original` is the form as we pre-filled it. Only boxes he actually
    changed are saved: a value we merely guessed (say, correspondence address
    = home address) must not land in the record as if someone had said so.

    Blanks never wipe a stored value: an empty box on the form usually means
    "not known yet", not "delete this".
    """
    now = datetime.now(IST)
    reference = f"CEA form {form.academic_year}"
    changed: list[str] = []

    def record(entity_type: str, entity: Any, column: str, new: Any, label: str) -> None:
        old = getattr(entity, column)
        if new is None or _same(old, new):
            return
        session.add(
            FieldHistory(
                entity_type=entity_type,
                entity_id=entity.id,
                field_name=column,
                old_value=None if old is None else _text(old),
                new_value=_text(new),
                source=ChangeSource.officer_entry,
                source_reference=reference,
                changed_at=now,
                changed_by_user_id=user_id,
                note="Edited on the CEA form",
            )
        )
        setattr(entity, column, new)
        changed.append(label)

    # Clean everything first, so one bad value saves nothing at all.
    problems: dict[str, str] = {}
    family_values: dict[str, Any] = {}
    for field, column in FAMILY_SAVE.items():
        if getattr(form, field) == getattr(original, field):
            continue
        try:
            family_values[column] = _clean(field, getattr(form, field))
        except FormProblem as e:
            problems.update(e.problems)
    child_values: list[tuple[FamilyMember, dict[str, Any]]] = []
    members = {m.id: m for m in family.members}
    before = {c.member_id: c for c in original.children}
    for index, child in enumerate(form.children):
        member = members.get(child.member_id) if child.member_id else None
        if member is None:
            continue
        was = before.get(child.member_id, CeaChildForm())
        values = {}
        for field, column in CHILD_SAVE.items():
            if getattr(child, field) == getattr(was, field):
                continue
            try:
                values[column] = _clean(field, getattr(child, field))
            except FormProblem as e:
                problems.update({f"children.{index}.{field}": v for v in e.problems.values()})
        if values:
            # The school details he typed belong to this year.
            values["academic_year"] = form.academic_year
            child_values.append((member, values))
    if problems:
        raise FormProblem(problems)

    for column, new in family_values.items():
        record("family", family, column, new, column.replace("_", " "))
    # The home address is shown as one block; keep it only if he rewrote it.
    if form.home_address.strip() and not _same(form.home_address, original.home_address):
        record("family", family, "address_line", form.home_address.strip(), "home address")

    if family.soldier is not None:
        for field, column in SOLDIER_SAVE.items():
            if getattr(form, field) != getattr(original, field):
                record("soldier", family.soldier, column, _clean(field, getattr(form, field)), f"soldier {column}")

    for member, values in child_values:
        first = member.full_name.split()[0]
        for column, new in values.items():
            # Ticking "hostel" off is a real answer, unlike a blank box.
            record("family_member", member, column, new, f"{first}'s {column.replace('_', ' ')}")

    if changed:
        session.add(
            AuditLog(
                user_id=user_id,
                action="cea.form_saved",
                entity_type="family",
                entity_id=family.id,
                occurred_at=now,
                details={"academic_year": form.academic_year, "changed": changed},
            )
        )
    return changed


# --- printing -------------------------------------------------------------------

INK = (0.07, 0.17, 0.45)  # a dark blue, so filled-in values stand out from the print


def _rupees(amount: int) -> str:
    """Indian grouping: 101250 -> 1,01,250."""
    text = str(int(amount or 0))
    if len(text) <= 3:
        return text
    head, tail = text[:-3], text[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


class _Writer:
    """Puts text in a box, shrinking or wrapping it so it never spills over."""

    def __init__(self, canvas: Any):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        self.c = canvas
        self.width_of = stringWidth
        self.c.setFillColorRGB(*INK)

    def text(self, x: float, y: float, value: Any, width: float = 200, size: float = 10) -> None:
        value = _text(value).strip()
        if not value:
            return
        while size > 6 and self.width_of(value, "Helvetica", size) > width:
            size -= 0.5
        while self.width_of(value, "Helvetica", size) > width and len(value) > 1:
            value = value[:-1]
        self.c.setFont("Helvetica", size)
        self.c.drawString(x, y, value)

    def lines(
        self, x: float, y: float, value: Any, width: float, max_lines: int,
        size: float = 9, leading: float = 11,
    ) -> None:
        """Word-wrap into at most `max_lines` lines, top line at `y`."""
        words = _text(value).replace("\n", " ").split()
        if not words:
            return
        while True:
            rows: list[str] = []
            for word in words:
                if rows and self.width_of(f"{rows[-1]} {word}", "Helvetica", size) <= width:
                    rows[-1] = f"{rows[-1]} {word}"
                else:
                    rows.append(word)
            if len(rows) <= max_lines or size <= 6:
                break
            size -= 0.5
            leading = max(leading - 0.5, size + 1)
        for i, row in enumerate(rows[:max_lines]):
            self.text(x, y - i * leading, row, width, size)

    def strike(self, x1: float, x2: float, y: float) -> None:
        self.c.setStrokeColorRGB(*INK)
        self.c.setLineWidth(1)
        self.c.line(x1, y, x2, y)


def _rank_name(form: CeaForm) -> str:
    return " ".join(p for p in (form.soldier_rank, form.soldier_name) if p)


def _title(child: CeaChildForm) -> str:
    return "Kumari" if child.relation == Relation.daughter.value else "Master"


def _school(child: CeaChildForm) -> str:
    return ", ".join(p for p in (child.school_name, child.school_place) if p)


def _period(child: CeaChildForm) -> str:
    if child.period_from and child.period_to:
        return f"{child.period_from} to {child.period_to}"
    return child.period_from or child.period_to


def _draw_cover(w: _Writer, form: CeaForm) -> None:
    w.text(104, 789, form.nok_name, 300)
    w.text(104, 761, _rank_name(form), 300)
    # The first line holds what fits; the rest goes on the lines below.
    first_line = _fit_words(w, form.home_address, 390, 10)
    w.text(154, 735, first_line, 390)
    rest = " ".join(form.home_address.split())[len(first_line):].strip(" ,")
    w.lines(60, 708, rest, 480, 2, size=10, leading=13)
    w.lines(180, 650, form.record_office, 360, 3, size=10, leading=13)
    w.text(180, 599, form.record_office_pincode, 120)

    w.text(280, 405, form.academic_year, 70)
    names = " & ".join(c.name for c in form.children)
    w.text(60, 380, names, 190)
    w.text(342, 380, form.service_number, 105)
    w.text(500, 380, form.soldier_rank, 58)
    w.text(106, 356, form.soldier_name, 185)
    w.text(140, 97, form.dated, 120)


def _fit_words(w: _Writer, value: str, width: float, size: float) -> str:
    """The longest run of whole words from the start of `value` that fits."""
    out = ""
    for word in value.split():
        candidate = f"{out} {word}".strip()
        if w.width_of(candidate, "Helvetica", size) > width:
            break
        out = candidate
    return out


def _draw_bill(w: _Writer, form: CeaForm) -> None:
    w.text(296, 520, _rank_name(form), 260)
    w.text(296, 494, form.service_number, 260)
    w.text(296, 468, form.unit, 260)
    w.text(296, 442, form.nok_name, 260)

    rows = [(320, 128), (265, 88)]  # (details table y, expenditure table y)
    for child, (y, money_y) in zip(form.children, rows):
        w.lines(123, y, child.name, 104, 3, size=9)
        w.text(233, y, child.date_of_birth, 65, 9)
        w.lines(303, y, child.current_class, 64, 3, size=9)
        w.text(373, y, form.academic_year, 60, 9)
        w.lines(438, y, _school(child), 120, 4, size=8, leading=10)

        w.lines(130, money_y + 4, _period(child), 132, 2, size=9)
        w.text(272, money_y, _rupees(child.cea_amount), 90)
        if child.hostel_amount:
            w.text(372, money_y, _rupees(child.hostel_amount), 90)
        w.text(474, money_y, _rupees(child.total), 88)

    w.text(474, 36, _rupees(sum(c.total for c in form.children)), 88, 11)


def _draw_bill_2(w: _Writer, form: CeaForm) -> None:
    first = form.children[0] if form.children else None
    board = first.school_board if first else ""
    w.text(358, 588, " / ".join(p for p in (board, form.school_state) if p), 125, 9)
    if first:
        w.text(186, 573, first.school_affiliation_code, 150, 9)

    w.text(304, 513, form.bank_account_holder, 250)
    bank = ", ".join(p for p in (form.bank_name, form.bank_branch, form.bank_address) if p)
    w.lines(304, 489, bank, 250, 2, size=9, leading=11)
    w.text(304, 441, form.bank_account_number, 250)
    w.text(304, 415, form.bank_ifsc, 250)

    w.lines(100, 340, form.home_address, 195, 4, size=9, leading=12)
    w.lines(305, 340, form.correspondence_address, 245, 4, size=9, leading=12)
    w.text(125, 276, form.permanent_pincode, 160)
    w.text(335, 276, form.correspondence_pincode, 160)
    w.text(190, 245, form.mobile, 200)
    w.text(130, 158, form.dated, 120)


def _draw_declaration(w: _Writer, form: CeaForm) -> None:
    for child, y in zip(form.children, (611, 572)):
        w.lines(111, y, child.name, 84, 3, size=8, leading=9)
        w.lines(201, y, _school(child), 63, 3, size=7, leading=8)
        w.lines(270, y, child.current_class, 52, 3, size=7, leading=8)
        w.text(328, y, child.date_of_birth, 47, 7)
        w.lines(381, y, _period(child), 55, 3, size=7, leading=8)
        w.text(443, y, _rupees(child.total), 70, 9)
    w.text(443, 528, _rupees(sum(c.total for c in form.children)), 70, 10)

    # "I am a Government Servant / NOT a Government Servant": strike the wrong half.
    if form.nok_is_govt_servant is False:
        w.strike(212, 313, 447)
    elif form.nok_is_govt_servant is True:
        w.strike(314, 472, 447)

    w.text(125, 297, form.dated, 100)
    w.text(402, 270, form.nok_name, 150, 9)
    w.text(402, 242, form.service_number, 150, 9)
    w.text(402, 215, form.soldier_rank, 150, 9)
    w.text(402, 187, form.soldier_name, 150, 9)


def _draw_school(w: _Writer, form: CeaForm, child: CeaChildForm) -> None:
    w.text(278, 555, child.name, 210)
    w.text(132, 528, child.admission_number, 88)
    w.text(262, 528, child.date_of_birth, 118)
    w.text(42, 502, form.nok_name, 170)
    w.text(398, 502, child.current_class, 42, 9)
    w.text(481, 502, child.section, 55)
    w.text(92, 475, child.roll_number, 93)
    w.text(452, 477, child.period_from, 85)
    w.text(52, 452, child.period_to, 85)
    w.text(287, 452, _school(child), 250)
    w.text(213, 407, child.school_affiliation_code, 62, 9)
    w.text(350, 407, child.school_board, 42, 8)


def render_pdf(form: CeaForm, source: Path = FORM_PDF) -> bytes:
    """The filled claim pack: cover letter, contingent bill (2 pages), self
    declaration, and one school certificate per child."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas

    def overlay(draw: Callable[[_Writer], None], size: tuple[float, float]):
        buffer = io.BytesIO()
        canvas = rl_canvas.Canvas(buffer, pagesize=size)
        draw(_Writer(canvas))
        canvas.save()
        buffer.seek(0)
        return PdfReader(buffer).pages[0]

    plan: list[tuple[int, Callable[[_Writer], None]]] = [
        (COVER, lambda w: _draw_cover(w, form)),
        (BILL, lambda w: _draw_bill(w, form)),
        (BILL_2, lambda w: _draw_bill_2(w, form)),
        (DECLARATION, lambda w: _draw_declaration(w, form)),
    ]
    for child in form.children or [CeaChildForm()]:
        plan.append((SCHOOL, lambda w, child=child: _draw_school(w, form, child)))

    writer = PdfWriter()
    for page_index, draw in plan:
        # A fresh read each time, so the school page can appear twice without
        # the two copies sharing one set of overlays.
        page = writer.add_page(PdfReader(source).pages[page_index])
        box = page.mediabox
        page.merge_page(overlay(draw, (float(box.width), float(box.height))))
    writer.add_metadata({"/Title": f"CEA claim {form.academic_year} - {form.nok_name}"})

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
