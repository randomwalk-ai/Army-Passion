"""Realistic Indian reference data used to build the mock database.

EVERYTHING HERE IS FAKE. No real person, service number or family appears.
Place names, regiments and coordinates are real only so the map and the
regional patterns look believable.
"""

from app.models.enums import DeathCauseCategory, Language

# --- Districts: (district, state, latitude, longitude, main language) ---------
DISTRICTS: list[tuple[str, str, float, float, Language]] = [
    # Punjab
    ("Ludhiana", "Punjab", 30.9010, 75.8573, Language.punjabi),
    ("Bathinda", "Punjab", 30.2110, 74.9455, Language.punjabi),
    ("Moga", "Punjab", 30.8158, 75.1711, Language.punjabi),
    ("Sangrur", "Punjab", 30.2458, 75.8421, Language.punjabi),
    ("Amritsar", "Punjab", 31.6340, 74.8723, Language.punjabi),
    ("Hoshiarpur", "Punjab", 31.5326, 75.9115, Language.punjabi),
    ("Gurdaspur", "Punjab", 32.0409, 75.4053, Language.punjabi),
    ("Patiala", "Punjab", 30.3398, 76.3869, Language.punjabi),
    ("Ferozepur", "Punjab", 30.9252, 74.6131, Language.punjabi),
    # Haryana
    ("Hisar", "Haryana", 29.1492, 75.7217, Language.hindi),
    ("Sirsa", "Haryana", 29.5349, 75.0280, Language.hindi),
    ("Karnal", "Haryana", 29.6857, 76.9905, Language.hindi),
    ("Rohtak", "Haryana", 28.8955, 76.6066, Language.hindi),
    ("Jind", "Haryana", 29.3159, 76.3146, Language.hindi),
    ("Bhiwani", "Haryana", 28.7930, 76.1397, Language.hindi),
    ("Mahendragarh", "Haryana", 28.2772, 76.1480, Language.hindi),
    ("Jhajjar", "Haryana", 28.6063, 76.6565, Language.hindi),
    # Uttar Pradesh
    ("Meerut", "Uttar Pradesh", 28.9845, 77.7064, Language.hindi),
    ("Gorakhpur", "Uttar Pradesh", 26.7606, 83.3732, Language.hindi),
    ("Varanasi", "Uttar Pradesh", 25.3176, 82.9739, Language.hindi),
    ("Jhansi", "Uttar Pradesh", 25.4484, 78.5685, Language.hindi),
    ("Bareilly", "Uttar Pradesh", 28.3670, 79.4304, Language.hindi),
    ("Azamgarh", "Uttar Pradesh", 26.0685, 83.1836, Language.hindi),
    # Uttarakhand
    ("Pauri Garhwal", "Uttarakhand", 30.1469, 78.7800, Language.hindi),
    ("Tehri Garhwal", "Uttarakhand", 30.3780, 78.4803, Language.hindi),
    ("Almora", "Uttarakhand", 29.5971, 79.6591, Language.hindi),
    ("Pithoragarh", "Uttarakhand", 29.5829, 80.2182, Language.hindi),
    # Himachal Pradesh
    ("Kangra", "Himachal Pradesh", 32.0998, 76.2691, Language.hindi),
    ("Mandi", "Himachal Pradesh", 31.7080, 76.9318, Language.hindi),
    ("Hamirpur", "Himachal Pradesh", 31.6861, 76.5213, Language.hindi),
    ("Bilaspur", "Himachal Pradesh", 31.3311, 76.7554, Language.hindi),
    # Rajasthan
    ("Jhunjhunu", "Rajasthan", 28.1289, 75.3995, Language.hindi),
    ("Sikar", "Rajasthan", 27.6094, 75.1399, Language.hindi),
    ("Alwar", "Rajasthan", 27.5530, 76.6346, Language.hindi),
    ("Jodhpur", "Rajasthan", 26.2389, 73.0243, Language.hindi),
    ("Bikaner", "Rajasthan", 28.0229, 73.3119, Language.hindi),
    # Maharashtra
    ("Satara", "Maharashtra", 17.6868, 74.0183, Language.marathi),
    ("Kolhapur", "Maharashtra", 16.7050, 74.2433, Language.marathi),
    ("Sangli", "Maharashtra", 16.8524, 74.5815, Language.marathi),
    ("Nashik", "Maharashtra", 19.9975, 73.7898, Language.marathi),
    # Tamil Nadu
    ("Coimbatore", "Tamil Nadu", 11.0168, 76.9558, Language.tamil),
    ("Madurai", "Tamil Nadu", 9.9252, 78.1198, Language.tamil),
    ("Salem", "Tamil Nadu", 11.6643, 78.1460, Language.tamil),
    ("Thanjavur", "Tamil Nadu", 10.7870, 79.1378, Language.tamil),
    # Kerala
    ("Thrissur", "Kerala", 10.5276, 76.2144, Language.malayalam),
    ("Kollam", "Kerala", 8.8932, 76.6141, Language.malayalam),
    ("Palakkad", "Kerala", 10.7867, 76.6548, Language.malayalam),
    # West Bengal
    ("Darjeeling", "West Bengal", 27.0360, 88.2627, Language.bengali),
    ("Purulia", "West Bengal", 23.3321, 86.3650, Language.bengali),
    ("Nadia", "West Bengal", 23.4710, 88.5565, Language.bengali),
    # Bihar
    ("Siwan", "Bihar", 26.2196, 84.3560, Language.hindi),
    ("Muzaffarpur", "Bihar", 26.1209, 85.3647, Language.hindi),
    ("Bhojpur", "Bihar", 25.5604, 84.5200, Language.hindi),
]

# Districts where the winter-fog two-wheeler accident pattern is seeded.
FOG_BELT_DISTRICTS = [
    "Ludhiana", "Bathinda", "Moga", "Sangrur", "Ferozepur", "Patiala",
    "Hisar", "Sirsa", "Karnal", "Rohtak", "Jind",
]

# --- Names, grouped by language so a family's names match its region ----------
MALE_FIRST_NAMES: dict[Language, list[str]] = {
    Language.hindi: [
        "Ramesh", "Suresh", "Rajesh", "Mahesh", "Dinesh", "Satpal", "Jagdish",
        "Om Prakash", "Rajbir", "Dharmendra", "Vijay", "Ravinder", "Krishan",
        "Balwant", "Surender", "Naresh", "Pawan", "Hoshiyar", "Mange Ram",
        "Birender", "Devender", "Yashpal", "Shyam Lal", "Bhim Singh",
    ],
    Language.punjabi: [
        "Gurpreet", "Jagtar", "Harbhajan", "Balbir", "Sukhwinder", "Manjit",
        "Kulwant", "Jaswant", "Darshan", "Avtar", "Amrik", "Rachhpal",
        "Hardeep", "Gurmail", "Satnam", "Baljinder",
    ],
    Language.tamil: [
        "Murugan", "Selvam", "Rajendran", "Kannan", "Arumugam", "Palanisamy",
        "Sivakumar", "Ramalingam", "Thangavel", "Saravanan", "Ganesan",
    ],
    Language.malayalam: [
        "Rajan", "Biju", "Vinod", "Pradeep", "Shaji", "Unnikrishnan",
        "Mohanan", "Sasidharan", "Jayachandran",
    ],
    Language.bengali: [
        "Subrata", "Tapan", "Dilip", "Ranjit", "Ashim", "Bikash", "Sanjoy",
        "Nirmal", "Prasenjit",
    ],
    Language.marathi: [
        "Dattatray", "Shivaji", "Balasaheb", "Sandeep", "Nitin", "Ganesh",
        "Vilas", "Ramrao", "Bhausaheb",
    ],
}

FEMALE_FIRST_NAMES: dict[Language, list[str]] = {
    Language.hindi: [
        "Sunita", "Kamlesh", "Santosh", "Bimla", "Sarita", "Rajbala",
        "Omwati", "Savitri", "Phool Kumari", "Nirmala", "Rekha", "Suman",
        "Meena", "Anita", "Pushpa", "Raj Rani", "Kaushalya", "Shakuntala",
    ],
    Language.punjabi: [
        "Harjit", "Baljit", "Surinder", "Gurmeet", "Paramjit", "Jaswinder",
        "Rajwinder", "Kuldeep", "Manpreet", "Charanjit",
    ],
    Language.tamil: [
        "Lakshmi", "Meenakshi", "Kalaivani", "Selvi", "Rajeswari", "Poongodi",
        "Vasanthi", "Chitra", "Amudha",
    ],
    Language.malayalam: [
        "Sheela", "Bindu", "Usha", "Latha", "Sindhu", "Ambika", "Girija",
        "Omana",
    ],
    Language.bengali: [
        "Mita", "Aparna", "Sumitra", "Rina", "Jhuma", "Kakoli", "Mousumi",
        "Anima",
    ],
    Language.marathi: [
        "Sunanda", "Mangal", "Shobha", "Vaishali", "Archana", "Sushma",
        "Chhaya", "Indubai",
    ],
}

SURNAMES: dict[Language, list[str]] = {
    Language.hindi: [
        "Yadav", "Singh", "Kumar", "Sharma", "Verma", "Tomar", "Chauhan",
        "Rathee", "Dahiya", "Malik", "Dagar", "Sangwan", "Nain", "Beniwal",
        "Rawat", "Negi", "Bisht", "Shekhawat",
    ],
    Language.punjabi: [
        "Sandhu", "Gill", "Dhillon", "Brar", "Sidhu", "Bajwa", "Randhawa",
        "Cheema", "Grewal", "Sekhon",
    ],
    Language.tamil: [
        "Subramanian", "Natarajan", "Pillai", "Gounder", "Thevar", "Nadar",
        "Chandrasekaran",
    ],
    Language.malayalam: ["Nair", "Menon", "Pillai", "Kurup", "Varghese", "Thomas"],
    Language.bengali: [
        "Das", "Ghosh", "Roy", "Mondal", "Sarkar", "Chakraborty", "Dutta", "Pal",
    ],
    Language.marathi: [
        "Patil", "Jadhav", "Pawar", "Shinde", "More", "Kadam", "Deshmukh",
        "Salunkhe",
    ],
}

# Children are a younger generation — names skew modern across regions.
BOY_CHILD_NAMES = [
    "Aryan", "Rohit", "Karan", "Aman", "Nikhil", "Harsh", "Vivek", "Ankit",
    "Deepak", "Akash", "Sahil", "Yash", "Rahul", "Abhishek", "Gaurav", "Tushar",
]
GIRL_CHILD_NAMES = [
    "Priya", "Neha", "Pooja", "Kavita", "Simran", "Jyoti", "Divya", "Komal",
    "Ritu", "Sneha", "Khushi", "Anjali", "Shreya", "Nisha", "Preeti", "Muskan",
]

# --- Service details ----------------------------------------------------------
# Other-rank and JCO ranks: the great majority of casualties.
RANKS_WEIGHTED = [
    ("Sepoy", 26), ("Lance Naik", 14), ("Naik", 16), ("Havildar", 16),
    ("Naib Subedar", 9), ("Subedar", 6), ("Subedar Major", 2),
    ("Rifleman", 5), ("Gunner", 3), ("Lieutenant", 1), ("Captain", 1),
    ("Major", 1),
]

REGIMENTS = [
    "Punjab Regiment", "Sikh Regiment", "Sikh Light Infantry",
    "Rajputana Rifles", "Rajput Regiment", "Jat Regiment", "Dogra Regiment",
    "Garhwal Rifles", "Kumaon Regiment", "Madras Regiment",
    "Maratha Light Infantry", "Mahar Regiment", "Bihar Regiment",
    "5 Gorkha Rifles", "The Grenadiers", "Assam Regiment",
    "Jammu & Kashmir Rifles", "Parachute Regiment", "Corps of Signals",
    "Army Service Corps", "Corps of EME", "Regiment of Artillery",
]

# Which regiments recruit most heavily from which state — keeps pairings sensible.
REGIMENT_BY_STATE: dict[str, list[str]] = {
    "Punjab": ["Punjab Regiment", "Sikh Regiment", "Sikh Light Infantry"],
    "Haryana": ["Jat Regiment", "Rajputana Rifles", "The Grenadiers"],
    "Uttar Pradesh": ["Rajput Regiment", "Kumaon Regiment", "Bihar Regiment"],
    "Uttarakhand": ["Garhwal Rifles", "Kumaon Regiment"],
    "Himachal Pradesh": ["Dogra Regiment", "Jammu & Kashmir Rifles"],
    "Rajasthan": ["Rajputana Rifles", "Rajput Regiment", "Regiment of Artillery"],
    "Maharashtra": ["Maratha Light Infantry", "Mahar Regiment"],
    "Tamil Nadu": ["Madras Regiment"],
    "Kerala": ["Madras Regiment", "Corps of Signals"],
    "West Bengal": ["5 Gorkha Rifles", "Bihar Regiment"],
    "Bihar": ["Bihar Regiment", "Rajput Regiment"],
}

# Posting stations: (place, state). Used for both soldiers and the colonel.
POSTING_STATIONS = [
    ("Siachen Base Camp", "Ladakh"), ("Leh", "Ladakh"), ("Kargil", "Ladakh"),
    ("Drass", "Ladakh"), ("Srinagar", "Jammu & Kashmir"),
    ("Baramulla", "Jammu & Kashmir"), ("Kupwara", "Jammu & Kashmir"),
    ("Rajouri", "Jammu & Kashmir"), ("Poonch", "Jammu & Kashmir"),
    ("Udhampur", "Jammu & Kashmir"), ("Pathankot", "Punjab"),
    ("Amritsar", "Punjab"), ("Ferozepur", "Punjab"), ("Jalandhar Cantt", "Punjab"),
    ("Ambala Cantt", "Haryana"), ("Hisar", "Haryana"), ("Jaipur", "Rajasthan"),
    ("Bikaner", "Rajasthan"), ("Jodhpur", "Rajasthan"), ("Suratgarh", "Rajasthan"),
    ("Dehradun", "Uttarakhand"), ("Ranikhet", "Uttarakhand"),
    ("Pithoragarh", "Uttarakhand"), ("Tawang", "Arunachal Pradesh"),
    ("Tezpur", "Assam"), ("Dinjan", "Assam"), ("Shillong", "Meghalaya"),
    ("Imphal", "Manipur"), ("Gangtok", "Sikkim"), ("Secunderabad", "Telangana"),
    ("Belgaum", "Karnataka"), ("Pune", "Maharashtra"), ("Nashik", "Maharashtra"),
    ("Wellington", "Tamil Nadu"), ("Jhansi", "Uttar Pradesh"),
    ("Babina", "Uttar Pradesh"), ("Meerut Cantt", "Uttar Pradesh"),
    ("Bareilly", "Uttar Pradesh"), ("Gorakhpur", "Uttar Pradesh"),
    ("Danapur", "Bihar"), ("Ranchi", "Jharkhand"), ("Delhi Cantt", "Delhi"),
]

FORMATIONS = [
    "15 Corps", "16 Corps", "14 Corps", "4 Corps", "33 Corps", "1 Corps",
    "2 Corps", "10 Corps", "21 Corps", "Southern Command", "Western Command",
]

# --- Causes of death: category -> plausible sub-causes ------------------------
CAUSES: dict[DeathCauseCategory, list[str]] = {
    DeathCauseCategory.battle_casualty: [
        "Enemy action", "IED blast", "Cross-border firing",
        "Counter-insurgency operation", "Ambush",
    ],
    DeathCauseCategory.physical_casualty: [
        "High altitude pulmonary oedema", "Avalanche", "Frostbite complications",
        "Drowning during exercise", "Heat stroke on duty", "Landslide",
    ],
    DeathCauseCategory.accident: [
        "Two-wheeler road accident", "Vehicle accident on duty",
        "Training accident", "Accidental weapon discharge", "Fall from height",
        "Electrocution", "Drowning",
    ],
    DeathCauseCategory.illness: [
        "Cardiac arrest", "Cancer", "Kidney failure", "Tuberculosis", "Stroke",
        "Liver disease",
    ],
    DeathCauseCategory.suicide: ["Self-inflicted"],
    DeathCauseCategory.natural_causes: ["Age-related illness"],
}

# How common each cause is, roughly.
CAUSE_WEIGHTS = [
    (DeathCauseCategory.accident, 32),
    (DeathCauseCategory.illness, 26),
    (DeathCauseCategory.physical_casualty, 18),
    (DeathCauseCategory.battle_casualty, 14),
    (DeathCauseCategory.suicide, 6),
    (DeathCauseCategory.natural_causes, 4),
]

WEATHER = [
    "Clear", "Dense fog", "Heavy snowfall", "Rain", "Extreme cold",
    "Heat wave", "Cloudy", "Thunderstorm",
]

BANKS = [
    "State Bank of India", "Punjab National Bank", "Canara Bank",
    "Bank of Baroda", "Union Bank of India", "Indian Bank", "HDFC Bank",
]

EDUCATION_LEVELS = [
    "Class 5", "Class 8", "Class 10", "Class 12", "ITI", "Diploma",
    "B.A. 1st year", "B.Sc. 2nd year", "B.Com. 3rd year", "Nursing course",
    "B.Tech 1st year", "Not studying",
]
