# Army Passion

A platform to help a retired Indian Army colonel support the widows and
families of soldiers who have died — finding the schemes each family qualifies
for, tracking applications, staying in touch, and drawing insights from the data.

**Current phase: mock data only.** Every record in this database is invented.
No real person, family, service number or bank account appears anywhere.

---

## What exists so far

- PostgreSQL + PostGIS and Redis, running in Docker
- The full database schema (16 tables) with Alembic migrations
- A mock data generator producing ~150 families with realistic Indian data
- 22 pytest tests that check the mock data matches the brief
- A health-check API
- The chat screen (Next.js) — sidebar, conversation area, file drop
- **Excel intake**: upload → a one-line summary of what each column means, which
  he confirms with a single button (and it is remembered for next time) → a
  preview of exactly what would change → the import, which records the old value
  of every changed field
- **The colonel's field list**: the database holds every field in his
  `LIST OF FIELDS` sheet (42 columns, his headings recognised exactly), plus
  the extra fields the CEA form needs, which are left empty for now. The sample
  Excel in `sample_data/` uses his exact column headings.
- **Children**: the Child1/Child2/Child3 columns become separate child
  records. On re-import a child is matched (name, then date of birth, then
  first name) and updated, never added twice; a child missing from a later
  sheet is never deleted.
- **Columns in the preview**: remove a column, or add a field the sheet
  doesn't have (with an optional value for every row).
- **Documents**: drop a PDF or photo, pick the family, then the whole family
  or one person in it, and the document type. Stored through the storage
  interface and listed per family.
- **Extra fields**: a column we have no home for is stored in the family's
  `extra_fields` pocket. The table structure never changes. Approved extra
  fields are reused so near-duplicates do not pile up.
- **LLM column mapping**: headings the rules do not recognise are sent to an
  LLM, which either matches them to a field or proposes storing them as new
  information. Only the HEADINGS are sent — never a row of family data. Runs
  against a fake by default, so it needs no API key. Set `LLM_PROVIDER=gemini`
  and `LLM_API_KEY` in `.env` to use the real one.
- **Voice notes**: upload → mock transcription → the LLM reads the transcript,
  suggests which family the call is about and proposes field changes it heard
  (e.g. a new phone or district) → he confirms which, if any, to apply → picks
  the family (or creates a new one, saved as a draft until complete)

- **Prototype** (`prototype/index.html`): a clickable, made-up copy of the
  screens, kept separate from the app. New features are tried there first;
  once agreed, the app is coded to match. Open the file in a browser — it
  needs no backend.

- **Home dashboard** (`/`): the key numbers (families, registered applicants,
  who can claim CEA, stuck applications, missing details, children turning 18)
  and the four main actions. The numbers come from `GET /api/dashboard` as a
  list, so a new number can be added without changing the screen.
- **Upload a sheet** (`/upload`): the Excel flow in three clear steps. Extra
  columns in his sheet get an "Add to database / Leave out" choice each, and
  the fields his sheet is missing are listed (they stay empty).
- **All families** (`/families`, also on Home): the database as one table,
  like his Excel sheet. Search, filter (e.g. "No documents yet"), sort by a
  column. Switch on **Editing** to correct a value in place; it is checked the
  same way as an import and the old value is kept in history. Tap a name to
  see the whole family and its documents (works well on a phone).
- **Supporting documents**: every family keeps **1 to 4** documents (PDF or
  photo). Required when adding a family; managed from the family panel or
  the CEA claim. Stored on local disk for now (`STORAGE_PROVIDER=local`); the
  blob-storage settings (`S3_*` in `.env`) are placeholders until it is connected.
- **Add a family** (`/families/new`): a simple form; only the two names and
  one document are needed. Uses the same cleaning rules as the Excel import, warns if the family
  looks like one already in the system, and records the officer as the source.
- **Eligibility** (`/eligibility`): every family checked against every scheme,
  with the same four answers for each (can claim · details missing · can claim
  later · cannot claim). One card per scheme, a column per scheme in the
  families table, and a "What they can claim" section in each family's panel.
  CEA is the first scheme; to add one, see `backend/app/services/eligibility.py`.
- **CEA claims** (`/cea`): every family checked against the Children Education
  Allowance rules for a chosen academic year (two eldest children, KG to 12, up
  to age 20, from 2017-18, monthly rates incl. hostel and divyang). The rules
  live in `backend/app/data/cea_scheme.json`, not in code. Pick a family to get
  the claim form pre-filled; edits are saved back to the record (old values kept
  in history), and **Download PDF** writes the values onto the official scanned
  form in `backend/CEA-Application/CEA 2026.pdf`. Tick **Add these documents
  to the end of the PDF** to get the claim and the family's supporting
  documents as one file.
- **Voice notes**: shown as "coming soon" on the menu and Home. The voice-note
  flow still works by dropping a recording on the **Assistant** (`/assistant`).

> **Developers:** how the dashboard, upload, add-a-family and CEA claim pieces
> work — the rules file, the eligibility engine, saving with history, and how
> to move text on the PDF — is explained in
> [`docs/dashboard-and-cea.md`](docs/dashboard-and-cea.md).
>
> **Explaining the system to someone?** Open
> [`docs/architecture/index.html`](docs/architecture/index.html) in a browser
> (double-click it; no server needed). It shows the layers, the core loop,
> wireframes of each screen, the data flows and the main tables.

Not built yet: talking points, the map, applications tracking, philanthropist matching,
WhatsApp, login, and the real external services.

---

## Setup (one time)

You need **Docker Desktop**, **Python 3.11+** and **Node.js** installed.

```powershell
# 1. Start the database and Redis
docker compose up -d

# 2. Copy the environment file and review it
copy .env.example .env

# 3. Create the Python environment and install packages
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Create the database tables
.venv\Scripts\python.exe -m alembic upgrade head

# 5. Fill the database with mock data
.venv\Scripts\python.exe -m seed.generate --reset

# 6. Install the frontend packages
cd ..\frontend
npm install
```

---

## Everyday commands

### Frontend (from the `frontend` folder)

| What you want | Command |
|---|---|
| Start the screen | `npm run dev` then open <http://localhost:3000> |
| Change the name shown in the menu | copy `.env.example` to `.env.local` and edit `NEXT_PUBLIC_USER_NAME` |
| Check it compiles | `npm run build` |

### Backend

All of these are run from the `backend` folder.

| What you want | Command |
|---|---|
| Start the database and Redis | `docker compose up -d` (from the project root) |
| Stop them | `docker compose down` (from the project root) |
| Rebuild the mock data from scratch | `.venv\Scripts\python.exe -m seed.generate --reset` |
| Make a sample Excel to test uploads | `.venv\Scripts\python.exe -m seed.make_sample_excel` |
| Make sample recordings to test voice notes | `.venv\Scripts\python.exe -m seed.make_sample_audio` |
| Run the tests | `.venv\Scripts\python.exe -m pytest` |
| Start the API | `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8010` |
| Open a SQL prompt | `docker exec -it army_passion_db psql -U army -d army_passion` |
| Create a new migration after changing models | `.venv\Scripts\python.exe -m alembic revision --autogenerate -m "what changed"` |
| Apply migrations | `.venv\Scripts\python.exe -m alembic upgrade head` |

### Checking it works

With the API running, open <http://localhost:8010/health/db>. You should see the
PostGIS version and the row counts:

```json
{"status": "ok", "postgis": "3.4 ...", "families": 150, "soldiers": 150, "mock_schemes": 10}
```

---

## Ports

The database uses **5434**, not the usual 5432, because other projects on this
machine already use 5432 and 5433. Redis uses **6380**, and the API uses
**8010** because something else on this machine answers on 8000.

| Service | Port | Connection |
|---|---|---|
| PostgreSQL + PostGIS | 5434 | `postgresql://army:army_dev_password@localhost:5434/army_passion` |
| Redis | 6380 | `redis://localhost:6380/0` |
| API (when running) | 8010 | <http://localhost:8010> |
| Frontend (when running) | 3000 | <http://localhost:3000> |

---

## What is in the mock data

Roughly, after a fresh `seed.generate --reset`:

| | Count |
|---|---|
| Families | 150 (including 3 deliberate near-duplicates) |
| Family members | ~425, of which 12 children turn 18 within three months |
| Soldiers with posting histories | 150, ~500 postings |
| MOCK schemes | 10 |
| Applications | ~235, of which ~36 are stuck too long |
| Documents | ~660 |
| Call notes and voice transcripts | ~280, in 6 languages with English translations |
| Philanthropists | 12, with ~49 proposed family matches |
| Data-quality problems | ~22 families flagged |

Deliberate patterns planted in the data:

- **Winter fog accidents** — two-wheeler deaths in foggy December/January in
  the Punjab and Haryana belt (Ludhiana, Bathinda, Sirsa, Hisar, Jind…), so the
  seasonal insight has something real to find.
- **Children turning 18** — twelve children cross 18 in the next three months,
  which is what the "becomes eligible later" alert must catch.
- **Shared postings** — about a third of soldiers served where the colonel
  served, in overlapping years. Talking points are built from these overlaps.
- **Regional consistency** — names, languages and regiments match the family's
  state. A Punjabi family in Ludhiana, a Malayalam family in Palakkad.

### Important caveats

- **Every scheme is invented.** Codes start with `MOCK-`, names contain "MOCK",
  and `schemes.is_mock` is `true` on all of them. Real KSB and state rules will
  replace them entirely.
- **Eligibility results are intentionally empty.** That table is the output of
  the rules engine, which is the next piece of work. Filling it with made-up
  verdicts would hide bugs in the engine.

---

## Project layout

```
army-passion/
├─ CLAUDE.md               the project brief (read first)
├─ docker-compose.yml      PostgreSQL/PostGIS + Redis
├─ .env.example            copy to .env; never commit .env
├─ sample_data/             fake files for testing uploads
│  ├─ widows_sheet_sample.xlsx   a messy "colonel's sheet"
│  ├─ widows_sheet_with_extra_columns.xlsx  same, plus 3 unknown columns
│  └─ voice/                     silent recordings, named after what they say
├─ frontend/                the chat screen (Next.js + Tailwind)
│  └─ src/
│     ├─ app/page.tsx       the screen itself, holds the state
│     ├─ components/        Sidebar, Conversation, PromptBox, ColumnMapping
│     └─ lib/
│        ├─ files.ts        decides if a dropped file is Excel or audio
│        └─ api.ts          calls the backend
└─ backend/
   ├─ app/
   │  ├─ config.py         settings read from .env
   │  ├─ db.py             database engine and sessions
   │  ├─ main.py           FastAPI app
   │  ├─ api/
   │  │  ├─ imports.py     Excel upload, mapping, preview, import
   │  │  ├─ voice.py       voice note upload and filing
   │  │  └─ families.py    family search, for the picker
   │  ├─ services/
   │  │  ├─ storage.py     file storage interface (local disk now, S3 later)
   │  │  ├─ speech.py      speech-to-text interface (mock now, Bhashini later)
   │  │  ├─ excel_reader.py reads untidy sheets into plain rows
   │  │  ├─ column_mapping.py guesses what each column means
   │  │  ├─ row_parser.py  cleans up messy dates, phones and amounts
   │  │  ├─ matching.py    is this row a family we already have?
   │  │  ├─ import_preview.py works out what would change
   │  │  └─ import_apply.py writes it, recording every old value
   │  └─ models/           the database tables
   │     ├─ enums.py       every controlled vocabulary
   │     ├─ people.py      users, soldiers, postings
   │     ├─ family.py      families and their members
   │     ├─ scheme.py      schemes and eligibility results
   │     ├─ application.py applications and stage history
   │     ├─ document.py    uploaded documents and AI extractions
   │     ├─ interaction.py calls, voice notes, visits
   │     ├─ philanthropist.py donors and matches
   │     └─ history.py     field history, audit log, data-quality issues
   ├─ alembic/             database migrations
   ├─ seed/
   │  ├─ reference_data.py Indian names, districts, regiments, causes
   │  ├─ mock_schemes.py   the 10 invented schemes and their rules
   │  ├─ mock_transcripts.py sample call notes in 6 languages
   │  └─ generate.py       builds the whole mock database
   └─ tests/               pytest checks on the mock data
```

---

## Two rules worth repeating

**Family data is never overwritten.** Every change writes a row to
`field_history` with the old value, the new value, where it came from
(Excel import, phone call, voice note, officer, OCR), when, and who did it.

**Eligibility rules are data, not code.** They live in the `schemes.rules` JSON
column so a new scheme can be added without changing any Python. The engine
that reads them is deterministic and will be covered by unit tests.
