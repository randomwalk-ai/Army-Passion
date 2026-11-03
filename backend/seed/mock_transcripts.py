"""Sample call notes and voice-note transcripts. All invented.

Each entry has the original text in the family's language, an English
translation, a short English summary, and the structured facts an extractor
should have pulled out of it. The `{widow}` and `{child}` placeholders are
filled in with the family's own names when the row is created.
"""

from app.models.enums import InteractionType, Language

TRANSCRIPTS: list[dict] = [
    {
        "language": Language.hindi,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "नमस्ते साहब। जी, मैं {widow} बोल रही हूँ। बच्चे ठीक हैं। "
            "{child} का दाखिला कॉलेज में हो गया है, फीस भरनी है लेकिन पैसे की "
            "दिक्कत है। पेंशन आ रही है पर बैंक वाले कागज़ माँग रहे हैं।"
        ),
        "english": (
            "Namaste sir. Yes, this is {widow} speaking. The children are well. "
            "{child} has got admission in college, the fees have to be paid but "
            "money is a problem. The pension is coming but the bank is asking "
            "for documents."
        ),
        "summary": (
            "Child admitted to college; family needs help with fees. Bank is "
            "asking for additional documents before releasing pension."
        ),
        "extracted": {
            "child_started_college": True,
            "needs_education_support": True,
            "bank_document_issue": True,
        },
        "sentiment": "worried",
        "follow_up": True,
        "follow_up_note": "Check education scholarship eligibility and help with bank documents.",
    },
    {
        "language": Language.hindi,
        "interaction_type": InteractionType.voice_note,
        "original": (
            "साहब जी, प्रणाम। दवाई का खर्चा बहुत हो गया है। मेरी तबियत ठीक "
            "नहीं रहती, घुटनों में दर्द है। गाँव से शहर जाना मुश्किल है। "
            "कोई मदद मिल सके तो बता दीजिए।"
        ),
        "english": (
            "Sir, greetings. The cost of medicines has become very high. My "
            "health is not good, there is pain in my knees. Travelling from the "
            "village to the city is difficult. Please let me know if any help "
            "is available."
        ),
        "summary": "Widow reports ongoing medical expenses and mobility difficulty.",
        "extracted": {
            "medical_need": True,
            "mobility_difficulty": True,
            "travel_to_city_difficult": True,
        },
        "sentiment": "distressed",
        "follow_up": True,
        "follow_up_note": "Assess for medical grant. Consider a volunteer field visit instead of asking her to travel.",
    },
    {
        "language": Language.english,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "Good morning sir. Thank you for calling. We received the amount "
            "last month, it came into the account properly. {child} is "
            "preparing for the NDA examination. We are managing well."
        ),
        "english": (
            "Good morning sir. Thank you for calling. We received the amount "
            "last month, it came into the account properly. {child} is "
            "preparing for the NDA examination. We are managing well."
        ),
        "summary": "Payment received successfully. Child preparing for NDA. No immediate needs.",
        "extracted": {
            "payment_received": True,
            "child_preparing_competitive_exam": "NDA",
            "immediate_need": False,
        },
        "sentiment": "positive",
        "follow_up": False,
        "follow_up_note": None,
    },
    {
        "language": Language.punjabi,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ। ਅਸੀਂ ਠੀਕ ਹਾਂ। ਕੁੜੀ ਦਾ ਵਿਆਹ ਅਗਲੇ ਸਾਲ ਕਰਨਾ ਹੈ, "
            "ਪੈਸੇ ਦਾ ਇੰਤਜ਼ਾਮ ਕਰਨਾ ਪੈਣਾ ਹੈ। ਜ਼ਮੀਨ ਥੋੜ੍ਹੀ ਹੈ, ਠੇਕੇ ਤੇ ਦਿੱਤੀ ਹੋਈ ਹੈ।"
        ),
        "english": (
            "Sat Sri Akal ji. We are fine. My daughter's marriage is to be done "
            "next year, arrangements for money have to be made. We have a little "
            "land, it has been given out on lease."
        ),
        "summary": "Daughter's marriage planned next year; family needs financial help. Small leased landholding is the income source.",
        "extracted": {
            "daughter_marriage_planned": True,
            "marriage_expected_year": "next_year",
            "income_source": "leased_agricultural_land",
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Check daughter's marriage assistance scheme well before the wedding date.",
    },
    {
        "language": Language.tamil,
        "interaction_type": InteractionType.voice_note,
        "original": (
            "வணக்கம் சார். வீட்டின் கூரை மழையில் சேதமாகிவிட்டது. "
            "சரி செய்ய வேண்டும். பையன் ஐ.டி.ஐ. படிக்கிறான். "
            "பென்ஷன் சரியாக வருகிறது."
        ),
        "english": (
            "Greetings sir. The roof of the house was damaged in the rain. It "
            "needs to be repaired. My son is studying at the ITI. The pension "
            "is coming properly."
        ),
        "summary": "House roof damaged by rain and needs repair. Son studying at ITI. Pension is regular.",
        "extracted": {
            "house_repair_needed": True,
            "damage_cause": "rain",
            "child_in_iti": True,
            "pension_regular": True,
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Assess for house repair grant.",
    },
    {
        "language": Language.hindi,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "जी साहब। गाँव में सब ठीक है। लेकिन कागज़ जमा करने के लिए "
            "जिला सैनिक बोर्ड के तीन चक्कर लगा चुके हैं, कोई जवाब नहीं मिलता। "
            "बेटा काम पर बाहर गया हुआ है।"
        ),
        "english": (
            "Yes sir. Everything is fine in the village. But we have already "
            "made three trips to the District Sainik Board to submit the "
            "papers, and get no reply. My son has gone outside for work."
        ),
        "summary": "Application stuck at the District Sainik Board despite three visits. Son has migrated for work.",
        "extracted": {
            "application_stuck": True,
            "visits_made": 3,
            "stuck_at": "district_sainik_board",
            "son_migrated_for_work": True,
        },
        "sentiment": "frustrated",
        "follow_up": True,
        "follow_up_note": "Escalate with the District Sainik Board directly. Family should not have to travel again.",
    },
    {
        "language": Language.malayalam,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "നമസ്കാരം സാർ. ഞങ്ങൾ സുഖമായിരിക്കുന്നു. മകൾ നഴ്സിംഗ് "
            "പഠിക്കുന്നു. ബാങ്ക് അക്കൗണ്ട് മാറ്റിയിട്ടുണ്ട്, പുതിയ നമ്പർ തരാം."
        ),
        "english": (
            "Greetings sir. We are well. My daughter is studying nursing. The "
            "bank account has been changed, I will give the new number."
        ),
        "summary": "Daughter studying nursing. Bank account has changed — new details need to be recorded.",
        "extracted": {
            "child_in_nursing_course": True,
            "bank_account_changed": True,
        },
        "sentiment": "positive",
        "follow_up": True,
        "follow_up_note": "Update bank details on record before the next payment run.",
    },
    {
        "language": Language.marathi,
        "interaction_type": InteractionType.voice_note,
        "original": (
            "नमस्कार साहेब. इकडे सगळं ठीक आहे. मुलगा बारावीला आहे, "
            "अभ्यास चांगला करतोय. शेतीतून फार उत्पन्न नाही यावर्षी, "
            "पाऊस कमी झाला."
        ),
        "english": (
            "Greetings sir. Everything is fine here. My son is in the twelfth "
            "standard and is studying well. There is not much income from "
            "farming this year, the rains were poor."
        ),
        "summary": "Son in Class 12 and doing well. Farm income down this year due to poor rainfall.",
        "extracted": {
            "child_in_class_12": True,
            "income_reduced": True,
            "income_reduction_reason": "poor_rainfall",
        },
        "sentiment": "neutral",
        "follow_up": False,
        "follow_up_note": None,
    },
    {
        "language": Language.bengali,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "নমস্কার স্যার। আমরা ভালো আছি। ছোট ছেলেটির শরীর ভালো নয়, "
            "ডাক্তার দেখাতে হয় প্রতি মাসে। টাকা অনেক খরচ হয়ে যায়।"
        ),
        "english": (
            "Greetings sir. We are well. My younger son's health is not good, "
            "he has to be shown to the doctor every month. A lot of money gets "
            "spent."
        ),
        "summary": "Younger son needs monthly medical care; recurring cost is a strain.",
        "extracted": {
            "child_health_issue": True,
            "medical_visits": "monthly",
            "recurring_medical_cost": True,
        },
        "sentiment": "worried",
        "follow_up": True,
        "follow_up_note": "Check disabled child allowance and medical grant. Ask for the medical certificate.",
    },
    {
        "language": Language.english,
        "interaction_type": InteractionType.field_visit,
        "original": (
            "Visited the family at their home. The house is in reasonable "
            "condition. The widow has started a small tailoring business from "
            "home and earns around four thousand rupees a month. Both children "
            "are in the village school. She asked whether a sewing machine "
            "loan is available."
        ),
        "english": (
            "Visited the family at their home. The house is in reasonable "
            "condition. The widow has started a small tailoring business from "
            "home and earns around four thousand rupees a month. Both children "
            "are in the village school. She asked whether a sewing machine "
            "loan is available."
        ),
        "summary": "Field visit: widow running a home tailoring business earning ~₹4,000/month. Children in school. Asked about equipment support.",
        "extracted": {
            "widow_self_employed": True,
            "business_type": "tailoring",
            "monthly_earning": 4000,
            "equipment_support_requested": True,
        },
        "sentiment": "positive",
        "follow_up": True,
        "follow_up_note": "Check vocational/livelihood scheme and possible philanthropist match for equipment.",
    },
    {
        "language": Language.hindi,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "साहब, फ़ोन नंबर बदल गया है, यह नया नंबर लिख लीजिए। "
            "हम अब बेटी के पास शहर में रहते हैं, गाँव का पता पुराना हो गया।"
        ),
        "english": (
            "Sir, the phone number has changed, please note this new number. "
            "We now live with our daughter in the city, the village address is "
            "out of date."
        ),
        "summary": "Phone number and address have both changed — family has moved in with their daughter in the city.",
        "extracted": {
            "phone_changed": True,
            "address_changed": True,
            "now_living_with": "daughter",
        },
        "sentiment": "neutral",
        "follow_up": True,
        "follow_up_note": "Update phone and address on record; old address is stale.",
    },
    {
        "language": Language.hindi,
        "interaction_type": InteractionType.phone_call,
        "original": (
            "जी, आपने पिछली बार कहा था कि कागज़ भेज देंगे। वो आ गए थे। "
            "धन्यवाद साहब। और कुछ ज़रूरत नहीं है अभी।"
        ),
        "english": (
            "Yes, last time you said you would send the papers. They arrived. "
            "Thank you sir. Nothing else is needed right now."
        ),
        "summary": "Papers sent earlier were received. No pending needs.",
        "extracted": {"documents_received": True, "immediate_need": False},
        "sentiment": "positive",
        "follow_up": False,
        "follow_up_note": None,
    },
]
