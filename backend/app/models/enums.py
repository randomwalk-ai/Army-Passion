"""Controlled vocabularies used across the database.

These are stored as plain strings with a CHECK-style Enum in PostgreSQL so the
values stay readable in SQL and in exports.
"""

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    colonel = "colonel"
    officer = "officer"
    volunteer = "volunteer"


class Language(str, enum.Enum):
    hindi = "hindi"
    english = "english"
    tamil = "tamil"
    punjabi = "punjabi"
    malayalam = "malayalam"
    bengali = "bengali"
    marathi = "marathi"


class DeathCauseCategory(str, enum.Enum):
    battle_casualty = "battle_casualty"
    physical_casualty = "physical_casualty"
    accident = "accident"
    illness = "illness"
    suicide = "suicide"
    natural_causes = "natural_causes"
    other = "other"


class DutyStatus(str, enum.Enum):
    on_duty = "on_duty"
    on_leave = "on_leave"
    unknown = "unknown"


class Relation(str, enum.Enum):
    """Relationship of a family member to the deceased soldier."""

    widow = "widow"
    son = "son"
    daughter = "daughter"
    father = "father"
    mother = "mother"
    other_dependent = "other_dependent"


class EligibilityStatus(str, enum.Enum):
    eligible = "eligible"
    not_eligible = "not_eligible"
    eligible_later = "eligible_later"  # e.g. a child who turns 18 next year
    needs_data = "needs_data"  # a rule could not be decided, data is missing


class ApplicationStage(str, enum.Enum):
    """The delivery pipeline, in order."""

    form_filled = "form_filled"
    verified_signed = "verified_signed"
    submitted = "submitted"
    received = "received"
    money_credited = "money_credited"
    rejected = "rejected"


APPLICATION_STAGE_ORDER = [
    ApplicationStage.form_filled,
    ApplicationStage.verified_signed,
    ApplicationStage.submitted,
    ApplicationStage.received,
    ApplicationStage.money_credited,
]


class DocumentType(str, enum.Enum):
    death_certificate = "death_certificate"
    aadhaar = "aadhaar"
    pan = "pan"
    bank_passbook = "bank_passbook"
    discharge_book = "discharge_book"
    pension_payment_order = "pension_payment_order"
    marriage_certificate = "marriage_certificate"
    birth_certificate = "birth_certificate"
    school_certificate = "school_certificate"
    # Named by the CEA and DIAV grant forms.
    service_booklet = "service_booklet"
    marksheet = "marksheet"
    fee_receipt = "fee_receipt"
    contingent_bill = "contingent_bill"
    self_declaration = "self_declaration"
    cancelled_cheque = "cancelled_cheque"
    computer_invoice = "computer_invoice"
    passport_photo = "passport_photo"
    other = "other"


# What the colonel sees for each type.
DOCUMENT_TYPE_LABELS = {
    "service_booklet": "Service booklet",
    "pension_payment_order": "PPO (Pension Payment Order)",
    "death_certificate": "Death certificate",
    "marksheet": "Mark sheet",
    "school_certificate": "Certificate from school / principal",
    "fee_receipt": "Fee receipt",
    "bank_passbook": "Bank passbook",
    "cancelled_cheque": "Cancelled cheque",
    "contingent_bill": "Contingent bill (CEA)",
    "self_declaration": "Self declaration by NOK",
    "aadhaar": "Aadhaar card",
    "pan": "PAN card",
    "birth_certificate": "Birth certificate",
    "marriage_certificate": "Marriage certificate",
    "computer_invoice": "Computer invoice / bill",
    "passport_photo": "Passport photo",
    "discharge_book": "Discharge book",
    "other": "Other",
}


class DocumentStatus(str, enum.Enum):
    missing = "missing"
    uploaded = "uploaded"
    ai_extracted = "ai_extracted"
    officer_approved = "officer_approved"
    rejected = "rejected"


class InteractionType(str, enum.Enum):
    phone_call = "phone_call"
    voice_note = "voice_note"
    whatsapp_message = "whatsapp_message"
    field_visit = "field_visit"


class ChangeSource(str, enum.Enum):
    """Where a piece of information came from. Recorded on every change."""

    excel_import = "excel_import"
    phone_call = "phone_call"
    voice_note = "voice_note"
    officer_entry = "officer_entry"
    whatsapp = "whatsapp"
    document_ocr = "document_ocr"
    system = "system"
    seed = "seed"


class IssueCode(str, enum.Enum):
    missing_phone = "missing_phone"
    invalid_phone = "invalid_phone"
    invalid_date = "invalid_date"
    missing_date_of_death = "missing_date_of_death"
    possible_duplicate = "possible_duplicate"
    missing_document = "missing_document"
    outdated_information = "outdated_information"
    missing_address = "missing_address"
    missing_bank_details = "missing_bank_details"


class IssueSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class IssueStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    ignored = "ignored"


class PhilanthropistInterest(str, enum.Enum):
    education = "education"
    medical = "medical"
    marriage = "marriage"
    livelihood = "livelihood"
