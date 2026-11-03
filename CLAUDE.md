# Project brief: Army Passion

## What we're building
A platform that helps a retired Indian Army colonel support widows and families of soldiers who have died. Today he works manually from Excel sheets and re-processes everything with Gemini whenever something is missing or wrong. This platform replaces that with one system that finds the grants and schemes each family qualifies for, tracks their applications, keeps him in touch with families, and gives insights from the data. Around 1,500+ soldiers die every year, so the number of families keeps growing.

## Who uses it
- The colonel and his officers: web dashboard (the main user right now)
- Families (widows): later through WhatsApp, not an app. Many are not tech-savvy.
- Philanthropists: later, matched with families so they can donate
- Volunteers: later, for field visits

Approach: take the path of least resistance for families and the colonel. Keep everything simple.

## Core loop: identify → verify → connect → deliver → continue
1. Identify: import Excel data into one database (single source of truth). Automatic data-quality checks (missing phones, wrong dates, duplicates, missing documents) with a "needs attention" list. Existing data may be outdated.
2. Verify: documents uploaded (later via WhatsApp), details extracted by OCR + AI, cross-checked, then an officer approves. AI suggests, a human always decides.
3. Connect: the colonel keeps making phone calls himself, because families can get scared when the army calls. Before each call, the system gives him talking points from the data: shared postings, common colleagues, personal connections, and a known date or context to mention. Information from calls and voice notes (mostly Hindi and English, some other languages) is transcribed, translated and extracted into structured fields in the database.
4. Deliver: track each application through stages (form filled → verified/signed → submitted → received → money credited), with an alert when it is stuck too long. Store the KSB DAK ID where relevant.
5. Continue: an eligibility engine matches every family to every scheme. Families not eligible now may become eligible later (e.g. a child turns 18), so the system alerts when that happens. Stay in touch even with families who aren't eligible for anything: birthday wishes for children, festival and anniversary alerts, new policy updates.

Also:
- Geotagging and a map view of families
- Insights from data and history, e.g. where, how and in which season soldiers' deaths happen, so units can be warned
- Philanthropist matching (a priority): collect the data needed to match donors with families' needs

## Tech stack
- Frontend: Next.js (React) + TypeScript + Tailwind CSS, built as a PWA
- Backend: Python FastAPI, SQLAlchemy, Alembic migrations, Pydantic
- Database: PostgreSQL + PostGIS (locations and map queries)
- Background jobs and scheduled alerts: Celery + Redis
- File storage: S3-compatible (DigitalOcean Spaces later); local disk during development, behind a storage interface
- Maps: Leaflet
- Real integrations later: WhatsApp Business Platform (Cloud API), Bhashini or Sarvam AI for speech-to-text / translation / text-to-speech, an LLM API (Gemini / Claude / GPT) for summaries and extraction, Aadhaar eSign
- Hosting later: DigitalOcean, Bangalore region
- Local development: Docker Compose for PostgreSQL/PostGIS and Redis

## Current phase: build with mock data
- Use ONLY fake, realistic Indian data. Never real personal data.
- Every external service (WhatsApp, speech-to-text, translation, LLM, e-sign, geocoding, storage) sits behind an interface with a mock implementation, switchable to the real one later through environment variables.
- Mock data should include:
  - About 150 families: widow, children with dates of birth (some turning 18 soon), address with district, state and coordinates, preferred language (mostly Hindi/English, some Tamil, Punjabi, Malayalam, Bengali, Marathi)
  - The deceased soldier: name, rank, fake service number, regiment/unit, postings history (unit, place, years), date of death, cause category and sub-cause, place, weather, on duty or on leave
  - The colonel's own postings, overlapping with some soldiers' postings, so talking points can be generated
  - Deliberate data problems in about 10% of records: missing phones, invalid dates, duplicates, outdated information
  - 8–10 mock schemes with eligibility rules, clearly labelled MOCK (real rules will come later from official KSB and state documents)
  - Applications at different stages, some of them stuck
  - Sample call notes and voice-note transcripts in Hindi and English, with English translations
  - Death patterns that show up on the map (e.g. winter two-wheeler accidents in foggy districts of Punjab and Haryana)
  - A few philanthropists with interests (education, medical, marriage, livelihood) and preferred regions

## Rules for building
- Never overwrite family data. Keep history: every change stores the old value, new value, source (Excel import / call / voice note / officer), date, and who made it.
- The database holds the current form's fields plus extra columns for new information.
- Eligibility rules are stored as data, not hard-coded. They are deterministic and covered by unit tests.
- Talking points come from the data first (rule-based). An LLM only rephrases them later.
- Roles: admin, colonel, officer, volunteer. Keep an audit log of who did what.
- Indian formats: DD-MM-YYYY dates, +91 phone numbers, ₹, Asia/Kolkata time zone.
- UI: simple, large readable text, clear actions, mobile-friendly. English first, ready for Hindi later.
- Secrets go in .env (never committed). Provide a .env.example.
- Backend tests with pytest.

## How to work with me
- I'm learning, so briefly explain what you're doing and why, in simple words.
- Work in small steps. After each step, tell me how to run and check it.
- Ask before adding major libraries or changing the stack.
- Keep README.md updated with setup and run commands.
