"""MOCK welfare schemes.

*** EVERY SCHEME HERE IS INVENTED. ***
The names, amounts and rules are placeholders so the eligibility engine has
something to chew on. Real rules will come later from official KSB and state
government documents, and will replace these wholesale.

Rule shape (stored as data in schemes.rules, never as code):

    {"all": [ condition, ... ]}        every condition must pass
    {"any": [ condition, ... ]}        at least one must pass

A condition is:

    {"field": "<name>", "op": "<operator>", "value": <value>}

Fields the engine will know how to read:
    family.state, family.district, family.annual_income,
    family.monthly_pension_amount, family.has_bank_details
    soldier.cause_category, soldier.rank_group, soldier.years_since_death
    widow.age, widow.is_remarried
    children.count, children.count_studying,
    children.has_unmarried_daughter_18_plus, children.has_disabled_child,
    children.min_age, children.max_age

Operators: eq, neq, gt, gte, lt, lte, in, not_in, is_true, is_false.
"""

MOCK_SCHEMES: list[dict] = [
    {
        "code": "MOCK-PENURY-GRANT",
        "name": "MOCK Penury Relief Grant for Aged Widows",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "livelihood",
        "description": (
            "Monthly relief for widows above 65 with very low household income "
            "and no other recurring support."
        ),
        "benefit_amount": 4000,
        "benefit_description": "₹4,000 per month",
        "is_recurring": True,
        "rules": {
            "all": [
                {"field": "widow.age", "op": "gte", "value": 65},
                {"field": "family.annual_income", "op": "lte", "value": 120000},
                {"field": "widow.is_remarried", "op": "is_false", "value": True},
            ]
        },
        "required_documents": ["aadhaar", "bank_passbook", "death_certificate"],
    },
    {
        "code": "MOCK-EDU-SCHOLARSHIP",
        "name": "MOCK Education Scholarship for Children of Fallen Soldiers",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "education",
        "description": (
            "Annual scholarship for up to two studying children, from Class 1 "
            "to graduation."
        ),
        "benefit_amount": 30000,
        "benefit_description": "₹30,000 per year per child, maximum two children",
        "is_recurring": True,
        "rules": {
            "all": [
                {"field": "children.count_studying", "op": "gte", "value": 1},
                {"field": "children.min_age", "op": "gte", "value": 5},
                {"field": "children.max_age", "op": "lte", "value": 25},
            ]
        },
        "required_documents": ["school_certificate", "bank_passbook", "aadhaar"],
    },
    {
        "code": "MOCK-HIGHER-EDU-GRANT",
        "name": "MOCK Higher Education Grant (Age 18+)",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "education",
        "description": (
            "One-time grant towards college or professional course fees. A child "
            "becomes eligible the day they turn 18."
        ),
        "benefit_amount": 75000,
        "benefit_description": "₹75,000 one-time",
        "is_recurring": False,
        "rules": {
            "all": [
                {"field": "children.max_age", "op": "gte", "value": 18},
                {"field": "children.count_studying", "op": "gte", "value": 1},
                {"field": "family.annual_income", "op": "lte", "value": 500000},
            ]
        },
        "required_documents": ["school_certificate", "aadhaar", "bank_passbook"],
    },
    {
        "code": "MOCK-ORPHAN-GRANT",
        "name": "MOCK Orphan Child Maintenance Grant",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "livelihood",
        "description": "Monthly maintenance where no surviving parent is recorded.",
        "benefit_amount": 3500,
        "benefit_description": "₹3,500 per month per child",
        "is_recurring": True,
        "rules": {
            "all": [
                {"field": "family.has_surviving_widow", "op": "is_false", "value": True},
                {"field": "children.count", "op": "gte", "value": 1},
                {"field": "children.min_age", "op": "lt", "value": 21},
            ]
        },
        "required_documents": ["death_certificate", "birth_certificate", "aadhaar"],
    },
    {
        "code": "MOCK-DAUGHTER-MARRIAGE",
        "name": "MOCK Daughter's Marriage Assistance",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "marriage",
        "description": "One-time assistance for the marriage of an unmarried daughter aged 18 or above.",
        "benefit_amount": 100000,
        "benefit_description": "₹1,00,000 one-time, maximum two daughters",
        "is_recurring": False,
        "rules": {
            "all": [
                {
                    "field": "children.has_unmarried_daughter_18_plus",
                    "op": "is_true",
                    "value": True,
                },
                {"field": "family.annual_income", "op": "lte", "value": 400000},
            ]
        },
        "required_documents": ["aadhaar", "birth_certificate", "bank_passbook"],
    },
    {
        "code": "MOCK-MEDICAL-GRANT",
        "name": "MOCK Medical Treatment Grant",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "medical",
        "description": "Reimbursement towards treatment of a serious illness or disability in the family.",
        "benefit_amount": 150000,
        "benefit_description": "Up to ₹1,50,000 per case",
        "is_recurring": False,
        "rules": {
            "any": [
                {"field": "children.has_disabled_child", "op": "is_true", "value": True},
                {"field": "widow.has_disability", "op": "is_true", "value": True},
            ]
        },
        "required_documents": ["aadhaar", "bank_passbook", "other"],
    },
    {
        "code": "MOCK-DISABLED-CHILD-ALLOWANCE",
        "name": "MOCK Allowance for Disabled Children",
        "authority": "MOCK Kendriya Sainik Board",
        "category": "medical",
        "description": "Lifetime monthly allowance for a child with a certified disability.",
        "benefit_amount": 5000,
        "benefit_description": "₹5,000 per month",
        "is_recurring": True,
        "rules": {
            "all": [
                {"field": "children.has_disabled_child", "op": "is_true", "value": True},
            ]
        },
        "required_documents": ["aadhaar", "other"],
    },
    {
        "code": "MOCK-VOCATIONAL-TRAINING",
        "name": "MOCK Widow Vocational Training & Livelihood Support",
        "authority": "MOCK Rajya Sainik Board",
        "category": "livelihood",
        "description": "Course fees plus a stipend for widows under 50 taking up a skill course.",
        "benefit_amount": 50000,
        "benefit_description": "₹50,000 towards training and stipend",
        "is_recurring": False,
        "rules": {
            "all": [
                {"field": "widow.age", "op": "lte", "value": 50},
                {"field": "widow.is_remarried", "op": "is_false", "value": True},
                {"field": "family.annual_income", "op": "lte", "value": 300000},
            ]
        },
        "required_documents": ["aadhaar", "bank_passbook"],
    },
    {
        "code": "MOCK-HOUSE-REPAIR",
        "name": "MOCK House Repair and Renovation Grant",
        "authority": "MOCK Rajya Sainik Board",
        "category": "housing",
        "description": "One-time grant to repair the family home. Available once every ten years.",
        "benefit_amount": 200000,
        "benefit_description": "₹2,00,000 one-time",
        "is_recurring": False,
        "rules": {
            "all": [
                {"field": "family.annual_income", "op": "lte", "value": 250000},
                {"field": "soldier.years_since_death", "op": "gte", "value": 2},
            ]
        },
        "required_documents": ["aadhaar", "bank_passbook", "other"],
    },
    {
        "code": "MOCK-PUNJAB-EXGRATIA",
        "name": "MOCK Punjab State Ex-Gratia for Battle Casualties",
        "authority": "MOCK Punjab Rajya Sainik Board",
        "category": "ex_gratia",
        "description": (
            "State ex-gratia payable to families domiciled in Punjab where the "
            "death was a battle casualty."
        ),
        "benefit_amount": 1000000,
        "benefit_description": "₹10,00,000 one-time",
        "is_recurring": False,
        "rules": {
            "all": [
                {"field": "family.state", "op": "eq", "value": "Punjab"},
                {
                    "field": "soldier.cause_category",
                    "op": "eq",
                    "value": "battle_casualty",
                },
            ]
        },
        "required_documents": ["death_certificate", "aadhaar", "bank_passbook"],
    },
]
