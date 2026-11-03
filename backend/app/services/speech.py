"""Speech to text, behind an interface.

Right now a mock returns realistic transcripts without sending anything
anywhere. Later this becomes Bhashini or Sarvam AI, switched by an environment
variable. Nothing outside this file needs to change when that happens.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import settings
from app.models.enums import Language


@dataclass
class Transcription:
    text_original: str
    text_english: str
    language: Language
    confidence: int  # 0-100
    duration_seconds: int | None = None
    # Facts a later extraction step could pull out of the words.
    suggested_fields: dict[str, object] = field(default_factory=dict)
    provider: str = "mock"


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(
        self, audio: bytes, filename: str, language: Language | None = None
    ) -> Transcription: ...


# English only for now, as agreed. Each entry is what a real call sounds like.
MOCK_CALLS: list[dict] = [
    {
        "text": (
            "Good morning sir. Thank you for calling. We are managing. My son "
            "has got admission in the polytechnic college at Rohtak but the "
            "fees are twenty-two thousand and we are short. The pension is "
            "coming on time now."
        ),
        "summary": "Son admitted to polytechnic at Rohtak. Short of ₹22,000 for fees. Pension arriving on time.",
        "fields": {
            "child_started_college": True,
            "education_support_needed": True,
            "amount_needed": 22000,
            "pension_regular": True,
        },
        "sentiment": "worried",
        "follow_up": True,
        "follow_up_note": "Check education scholarship. Possible philanthropist match for ₹22,000 fees.",
    },
    {
        "text": (
            "Sir, I wanted to tell you my phone number has changed. The new "
            "number is nine eight seven six five four three two one zero. We "
            "have also shifted to my daughter's house in Karnal."
        ),
        "summary": "Phone number and address have changed. Family has moved to their daughter's house in Karnal.",
        "fields": {
            "phone_changed": True,
            "address_changed": True,
            "new_district": "Karnal",
            "now_living_with": "daughter",
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Update phone and address on record. Old address is stale.",
    },
    {
        "text": (
            "Namaste sir. The medical expenses are becoming very heavy. My "
            "younger son needs treatment every month at the district hospital "
            "and the travel itself costs a lot. We need some help."
        ),
        "summary": "Younger son needs monthly hospital treatment. Travel and medical costs are a strain.",
        "fields": {
            "medical_need": True,
            "child_health_issue": True,
            "medical_visits": "monthly",
            "travel_cost_burden": True,
        },
        "sentiment": "distressed",
        "follow_up": True,
        "follow_up_note": "Assess for medical grant and disabled child allowance. Ask for the medical certificate.",
    },
    {
        "text": (
            "Sir, we submitted all the papers at the district office three "
            "times but there is no reply. It has been four months now. My son "
            "has gone to Delhi for work so I am alone here."
        ),
        "summary": "Application stuck at the district office for four months despite three submissions. Widow living alone; son has migrated to Delhi for work.",
        "fields": {
            "application_stuck": True,
            "months_waiting": 4,
            "visits_made": 3,
            "living_alone": True,
            "son_migrated_for_work": True,
        },
        "sentiment": "frustrated",
        "follow_up": True,
        "follow_up_note": "Escalate with the District Sainik Board. She should not have to travel again.",
    },
    {
        "text": (
            "Everything is fine here sir. The money came into the account last "
            "month. My daughter is in class twelve and doing well in her "
            "studies. We do not need anything at the moment."
        ),
        "summary": "Payment received. Daughter in Class 12 and doing well. No immediate needs.",
        "fields": {
            "payment_received": True,
            "child_in_class_12": True,
            "immediate_need": False,
        },
        "sentiment": "positive",
        "follow_up": False,
        "follow_up_note": None,
    },
    {
        "text": (
            "Good morning sir. This is Anita Kumar calling from Bareilly. "
            "My phone number has changed, the new number is nine eight "
            "seven six five zero zero zero zero two. Everything else is fine."
        ),
        "summary": "Anita Kumar, Bareilly: phone number changed.",
        "fields": {"phone_changed": True, "new_phone": "9876500002"},
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Update phone number on record.",
    },
    {
        "text": (
            "Good afternoon sir. This is about Santosh Sangwan. I wanted to "
            "let you know our phone number has changed, the new number is "
            "nine eight seven six five zero zero zero zero one. We have also "
            "moved and are now staying in Hisar district with our son."
        ),
        "summary": "Santosh Sangwan: phone number changed, family has moved to Hisar district.",
        "fields": {
            "phone_changed": True,
            "new_phone": "9876500001",
            "address_changed": True,
            "new_district": "Hisar",
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Update phone and district on record.",
    },
    {
        "text": (
            "Sir, this is regarding Havildar Ram Kumar of nine Jat regiment. "
            "He passed away last month near Rohtak in a road accident. His "
            "wife is Kamlesh Devi. Nobody has contacted them yet."
        ),
        "summary": "Report of a new casualty: Havildar Ram Kumar, 9 Jat, road accident near Rohtak last month. Widow is Kamlesh Devi. No contact made yet.",
        "fields": {
            "new_family_report": True,
            "soldier_name": "Ram Kumar",
            "rank": "Havildar",
            "unit": "9 Jat",
            "cause_of_death": "Road accident",
            "district": "Rohtak",
            "widow_name": "Kamlesh Devi",
            "not_yet_contacted": True,
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "New family — create a draft record and make first contact.",
    },
]


class MockSpeechToText(SpeechToText):
    """Returns a realistic transcript. Sends nothing anywhere.

    The same audio always produces the same transcript, so the screen behaves
    predictably while we build it.
    """

    def transcribe(
        self, audio: bytes, filename: str, language: Language | None = None
    ) -> Transcription:
        # Choose by the content of the file, so re-uploading gives the same result.
        digest = hashlib.sha256(audio or filename.encode()).hexdigest()
        sample = MOCK_CALLS[int(digest[:8], 16) % len(MOCK_CALLS)]

        return Transcription(
            text_original=sample["text"],
            text_english=sample["text"],  # English only for now
            language=Language.english,
            confidence=88,
            # A rough guess: spoken English runs about 150 words a minute.
            duration_seconds=max(20, int(len(sample["text"].split()) / 150 * 60)),
            suggested_fields={
                "summary": sample["summary"],
                "extracted": sample["fields"],
                "sentiment": sample["sentiment"],
                "follow_up_needed": sample["follow_up"],
                "follow_up_note": sample["follow_up_note"],
            },
            provider="mock",
        )


def get_speech_to_text() -> SpeechToText:
    if settings.speech_to_text_provider == "mock":
        return MockSpeechToText()
    raise NotImplementedError(
        f"Speech provider '{settings.speech_to_text_provider}' is not built yet. "
        "Set SPEECH_TO_TEXT_PROVIDER=mock in your .env."
    )
