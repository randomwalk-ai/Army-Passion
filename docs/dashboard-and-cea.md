# Dashboard, upload, add-a-family and CEA claims — how it works

Developer notes for the features added on the `feature/dashboard-and-cea`
branch. Read this before changing any of them.

---

## The screens

| Page | File | What it does |
|---|---|---|
| `/` Home | `frontend/src/app/page.tsx` | Number tiles, a small families table, the main actions |
| `/families?filter=&family=` | `frontend/src/app/families/page.tsx` | The full families table (`family=ID` opens that family) |
| `/upload` | `frontend/src/app/upload/page.tsx` | Excel import in 3 steps |
| `/families/new` | `frontend/src/app/families/new/page.tsx` | Add one family by hand |
| `/schemes` (Schemes & grants) | `frontend/src/app/schemes/page.tsx` | Every scheme's four answers, and "check one family" |
| `/cea` | `frontend/src/app/cea/page.tsx` | Who can claim CEA, for a chosen year |
| `/cea/[familyId]?year=2025-26` | `frontend/src/app/cea/[familyId]/page.tsx` | The pre-filled claim, Save, Download PDF |
| `/assistant` | `frontend/src/app/assistant/page.tsx` | The older chat screen (drop files, voice notes) — unchanged, just moved |

Voice notes are shown as **"Coming soon"** in the menu and on Home. There is
no `/voice` page; the working voice flow is still on `/assistant`.

### Shared frontend pieces

- `components/AppShell.tsx` — the frame for every page (menu + scrolling content).
- `components/Sidebar.tsx` — the menu. Add a page by adding to `NAV`; set
  `soon: true` to show it greyed out with a "Soon" badge.
- `components/ui.tsx` — `PageHeader`, `Card`, `SectionTitle`, `Field` (text box
  with label, hint, error; `date` adds DD-MM-YYYY dashes as you type),
  `Choice` (big buttons instead of dropdowns), `Checkbox`, `Notice`, `Spinner`,
  button styles, and `errorText()` for friendly "server not reachable" messages.
- `components/FamilyTable.tsx` — the spreadsheet (see "The families table").
- `components/SupportingDocuments.tsx` — `SupportingDocuments` (a saved
  family's 1–4 files: list, view, add, remove) and `DocumentPicker` (files
  picked before the family exists, used by Add a family).
- `components/ThemeSwitch.tsx` + `lib/theme.ts` — a single **Dark mode** on/off
  switch at the bottom of the menu. Until it is pressed, the page follows the
  computer's setting; once pressed, the choice is set as `data-theme` on
  `<html>` and remembered in this browser. A tiny script in `app/layout.tsx`
  applies it before the page paints, so there is no white flash. Colours are
  tokens in `app/globals.css` (one set for light, one for dark) — always use the
  tokens (`bg-surface`, `text-muted`, ...), never hard-coded colours, and both
  themes work automatically.
- `lib/currentUser.ts` — the name and role shown in the menu and on Home.
  There is no login yet, so they come from `NEXT_PUBLIC_USER_NAME` /
  `NEXT_PUBLIC_USER_ROLE` in `frontend/.env.local` (see `frontend/.env.example`),
  defaulting to "Demo User". Never hard-code a real person's name in the
  screens; swap this for the logged-in user once login exists.
- `components/CeaStatusBadge.tsx` — CEA status with an icon + words (never colour alone).
- `lib/api.ts` — every call to the backend. Form endpoints throw `FormRejected`
  carrying `fieldErrors` (shown next to each box) and duplicate `matches`.

### UX rules we followed (please keep them)

- Plain words, large text (17px inputs), one obvious primary button per screen.
- Errors say what to do, next to the box they belong to.
- Short choices are big buttons, not dropdowns.
- Nothing is saved without a clear button press; success screens say what happened and what to do next.
- **Phone first** — most use is on a phone:
  - Design at 360px wide first; add `sm:` (640px+) for wider screens.
  - Tap targets at least 44px tall (`min-h-11`); no tiny underlined links as the only way to act.
  - Text boxes are 16px or more on phones, or iPhones zoom the page in
    (enforced in `globals.css`).
  - Nothing sideways-scrolls except deliberate swipe rows (`no-scrollbar`,
    e.g. the CEA tabs). Long codes wrap (`overflow-wrap` on `body`).
  - Sticky bottom bars use `pb-safe` so they clear the iPhone home bar; the
    page frame has `scroll-pb-44` so a focused box is never hidden behind one.
  - Full height uses `.app-height` (100vh with a 100dvh upgrade), not `h-dvh` alone.
  - Nothing important lives only in a hover tooltip — use a tappable
    "Why?" (`<details>`) instead.
  - Names use `autoCapitalize="words"`, codes like IFSC `"characters"`;
    numbers and dates open the number keypad (`inputMode`).

---

## Backend endpoints

| Endpoint | File | Notes |
|---|---|---|
| `GET /api/dashboard` | `app/api/dashboard.py` | Returns `stats: [{key, label, value, hint, tone, href}]` |
| `POST /api/families` | `app/api/families.py` + `app/services/family_create.py` | 201 created · 422 per-field errors · 409 possible duplicate |
| `GET /api/cea/eligibility?year=` | `app/api/cea.py` | Every non-draft family, sorted: can claim → details missing → later → cannot |
| `GET /api/cea/families/{id}/form?year=` | `app/api/cea.py` | Pre-filled form + verdict + list of empty boxes |
| `PUT /api/cea/families/{id}/form` | `app/api/cea.py` | Saves his edits back to the record (with history) |
| `POST /api/cea/pdf` | `app/api/cea.py` | Body = `{form, include_documents}`; returns the filled PDF (+ documents) |
| `GET /api/families/table` | `app/api/families.py` + `app/services/family_table.py` | `q, filter, sort, descending, page, page_size` → columns, rows, filter counts |
| `GET /api/families/{id}/row` | same | One family as a table row |
| `PATCH /api/families/{id}/cell` | same | `{key, value}` → 422 with a plain reason if the value is wrong |
| `GET /api/families/{id}/supporting-documents` | `app/api/documents.py` | `{minimum: 1, maximum: 4, documents}` |
| `POST /api/families/{id}/supporting-documents` | same | multipart `file` + `doc_type` · 409 when 4 already |
| `DELETE /api/families/{id}/supporting-documents/{doc}` | same | 409 if it is the last one |

### Dashboard tiles are a list on purpose

To add a number, append a `Stat(...)` in `dashboard.py`. The screen shows the
first two tiles large and the rest smaller — no frontend change needed.
`tone="attention"` adds a warning icon and border when the value is above 0;
`href` makes the tile clickable.

---

## Upload: extra and missing columns

The upload page reuses the existing import flow
(`ColumnMapping` → `ImportPreview`). The change is in
`frontend/src/components/ColumnMapping.tsx`:

- **Extra columns** (headings we have no field for): each gets
  **Add to database / Leave out**. Columns the system could name start as
  "Add"; ones it could not make sense of start as "Leave out" (so "S.No" etc.
  stay out). "Add" creates a custom field and the values go into the family's
  `extra_fields` JSON — the table structure never changes.
- **Missing fields** (fields we keep that the sheet has no column for): listed
  under "N fields missing from your sheet". They stay empty for new families;
  nothing already stored is wiped. A value for every row can still be added on
  the preview step ("add a column").

---

## Add a family

`family_create.check()` sends the typed values through the **same**
`parse_row()` cleaners as an Excel row, so dates, phones (+91), PIN codes and
IFSC codes are stored identically. Rules:

- Only `soldier_name` and `widow_name` are required.
- Wrongly typed values → 422 with `errors: {field_key: message}`
  (child fields are keyed `children.<index>.<field>`).
- A missing phone / date of death is **not** blocking: the family is saved and
  a `DataQualityIssue` is raised so it appears in "missing details".
- Before saving, `FamilyIndex.find()` (the import's matcher) looks for the same
  family. Score ≥ 40 → 409 with the matches; the form asks him, and resends
  with `confirm_not_duplicate: true` if he says it is a different family.
- History: a `__created__` row in `field_history` with source `officer_entry`,
  plus an `audit_log` row `family.create`.
- Empty child rows on the form are ignored.

---

## Eligibility: the list of schemes

`app/services/eligibility.py` holds `SCHEMES`. Each `Scheme` has a code,
name, description, the period it checks, the page to act on it, and
`check(session, families) -> {family_id: Verdict}`. Every scheme answers with
the same four statuses (`eligible`, `needs_data`, `eligible_later`,
`not_eligible`), plus a one-line `headline`, the `reasons` and an `amount`.

The screens only read this list, so **adding a scheme = writing its `check`
(rules in a data file, like `app/data/cea_scheme.json`, with unit tests) and
appending a `Scheme(...)`**. It then appears automatically:

- as a card on the Schemes & grants page, `/schemes` (`GET /api/eligibility`)
- as a column in the families table (`scheme.<CODE>`, with the verdict in `row.eligibility`)
- in each family's panel (`GET /api/families/{id}/eligibility`)

Shared look: `frontend/src/components/EligibilityBadge.tsx` (icon + words,
never colour alone) and `FamilyEligibility.tsx`.

---

## Supporting documents (1 to 4 per family)

- A `documents` row with `is_supporting = true` (migration `d4a9c1e8f2b6`).
  These are separate from the older per-document records the seed creates
  for the AI-extraction flow, so they never count towards the limit.
- The limits live in `app/api/documents.py` (`MIN_SUPPORTING`, `MAX_SUPPORTING`).
  The server enforces the maximum (409) and refuses to remove the last one
  (409: "add the replacement first"). The minimum for a **new** family is
  enforced by the Add-a-family form, which uploads the files right after the
  family is created; families from Excel start with none and show up under
  "No documents yet" (table filter and a Home tile).
- PDF, JPG, PNG, WebP up to 20 MB. Files go through `get_storage()`.

### Blob storage (not connected yet)

`STORAGE_PROVIDER=local` (default) writes to `./storage`. `STORAGE_PROVIDER=s3`
selects `S3Storage` in `app/services/storage.py`, a placeholder that reads
`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`
and stops with a clear message saying it is not built. To finish it: add
`boto3` and implement the four methods (`put_object`, `get_object`,
`delete_object`, `head_object`) with the same `folder/uuid.ext` keys.

### In the CEA PDF

`app/services/document_pack.py` → `append_documents(pdf, attachments)`:
PDFs are added page by page; photos are put on an A4 page (turned the right
way up) with a small caption. A file that is missing or cannot be opened gets
a page saying so, rather than failing the whole download.

---

## The families table

`app/services/family_table.py` holds `COLUMNS`: **every detail the database
holds**, so nothing is hidden (the table scrolls sideways). For each column:
where the value lives (`family`, `soldier`, `child`, `extra` for approved
custom fields, or `computed` such as Documents and Number of children), the
cleaner (the same `parse_phone`, `parse_date`, `parse_pincode`, `parse_ifsc`…
as the import), whether it is required, and its `group` — the heading it sits
under in the family panel (Next of kin, Soldier, Address, Children, Child 1,
Child 2, Child 3, Pension and bank, Unit contact, CEA, Other, Extra fields).
This includes the fields only the forms ask for (each child's school details,
govt servant, duty status...). Only system values (ids, map points,
timestamps) are left out. To add a column, add one
line there — the screen builds itself from the list. Approved extra fields
appear as columns automatically.

Profile: `completeness()` gives each family 0-100% — every column counts
(Documents = at least one, Number of children = at least one) except the
scheme answers and the details of children who don't exist. Rounded down, so
100% means nothing is missing. Shown as a ring after the name and at the top
of the family panel with the list of what is missing. Sorting by it
(`sort=profile`) is worked out in Python over all matching families, then
one page is cut out, so the order is right across pages.

Children: Child 1, 2 and 3 are the family's children **oldest first** (by
date of birth; children without one come last). A name typed into the next
empty child adds that child; other details of an empty child, or skipping a
child (Child 3 before Child 2), are refused. Setting a child's sex makes them
a son or daughter; Cause of death also files the soldier under a category;
GPS location also moves the family's map point.

Editing a cell: a blank box clears the value (allowed here because it is a
deliberate act) unless the column is required; an unchanged value writes
nothing; every change writes `field_history` (source `officer_entry`,
reference "Families table") and an `audit_log` row `family.update`.

On screen: the table is read-only, so a stray click can change nothing
(nothing in it is clickable except the ✏️). The ✏️ next to a name is the only
way in: it opens the family panel (side panel on a computer, bottom sheet on a
phone) with what they can claim, the documents, and every value with a
**Change** button. A value is saved only by pressing **Save**: Enter does
nothing, and Cancel, Esc or closing the panel throws the change away. On a
phone the table scrolls sideways with the name pinned.

---

## CEA (Children Education Allowance)

### Where the rules live

**`backend/app/data/cea_scheme.json`** — the rules are data, not code.

```json
"rules": {
  "eldest_children": 2,          // only the N eldest children (by date of birth)
  "min_age": 3, "max_age": 20,   // age on the first day of the academic year
  "max_class": 12,               // KG (=0) to Class 12
  "first_academic_year": 2017,   // 2017-18 onwards
  "academic_year_start_month": 4,// April–March
  "rates": [                      // monthly, in force from the date given
    {"from": "2017-07-01", "cea": 2250, "hostel": 6750, "divyang": 4500},
    {"from": "2024-01-01", "cea": 2813, "hostel": 8438, "divyang": 5625}
  ]
}
```

On first use, `ensure_cea_scheme()` copies this file into the `schemes` table
(code `CEA`, `is_mock = false`). **After that the database row is what counts.**
To change a rate on an existing database, update `schemes.rules` for code
`CEA` (or delete that row and it is recreated from the JSON).

Source documents: `backend/CEA-Application/CEA 2026.pdf` and `CEA GRANTS.png`.

### The engine — `app/services/cea.py`

Pure functions, no database needed, fully covered by `tests/test_cea.py`.
`evaluate(children, date_of_death, academic_year, rules)` returns a
`FamilyVerdict` with one `ChildVerdict` per child.

Per child, in this order:

1. No date of birth → **needs data** (we cannot tell if it is one of the eldest)
2. Not among the N eldest → **cannot claim**
3. Not studying (or class says "Not studying") → **cannot claim**
4. Older than `max_age` at the start of the year → **cannot claim**
5. Younger than `min_age` → **can claim later** (`becomes_eligible_on` = that birthday)
6. Class beyond 12 → **cannot claim**, unless the child is 16 or under, then **needs data** (a typing mistake)
7. Class far from the age (class > age − 3, or class < age − 12) → **needs data**
8. Otherwise **can claim**. Amount worked out month by month (handles a year
   across a rate change, and a death part-way through the year).
   Divyang → divyang rate instead of CEA rate. Hostel → hostel rate on top.
   Unknown class or hostel → still "can claim", with a `to_confirm` note.

Family level: before 2017-18 → cannot; no date of death → needs data; soldier
died after the year ended → cannot. Otherwise the family takes its best child's
status (can claim > needs data > later > cannot).

The class is read from `current_class`, falling back to `education_level`.
`class_number()` understands "Class 8", "8th", "Std. 10", "XII", "UKG",
"B.A. 1st year" (→ beyond school), "Not studying".

The year to claim by default is the **last completed** academic year, because
claims are sent after the year ends.

### The form — `app/services/cea_form.py`

- **`build_form()`** pre-fills every blank on the claim from the family,
  soldier and children. It picks the eligible children (max 2), or the two
  eldest if none are eligible, so the form is never empty.
- **`missing_fields()`** lists empty boxes. The frontend has the same list in
  `stillEmpty()` (in the form page) so it updates as he types — keep the two in step.
- **`save_form(session, family, form, original, user_id)`** writes edits back:
  - Only boxes that differ from `original` (the pre-filled form) are saved.
    A value we only guessed (e.g. correspondence address = home address) is
    never written to the record as if someone had said it.
  - Blank boxes never wipe stored values.
  - Every value is checked first; one bad value (e.g. a bad mobile) saves nothing.
  - Each change → a `field_history` row (source `officer_entry`, reference
    `CEA form 2025-26`), plus one `audit_log` row `cea.form_saved`.
  - Names, period, amounts and the form date are **not** saved to the record —
    they belong to this claim only.
  - What maps to what: `FAMILY_SAVE`, `SOLDIER_SAVE`, `CHILD_SAVE` at the top of the save section.
- **`render_pdf()`** draws the values onto the official pages:
  cover letter (page 3 of the source), contingent bill (pages 4–5),
  self-declaration (page 6), and the school certificate (page 7) **once per child**.
  Pages 1–2 (the rules) are not included.

### Changing where text lands on the PDF

The source PDF is a **scan** — no fillable boxes — so every value is placed by
position, in the `_draw_cover`, `_draw_bill`, `_draw_bill_2`,
`_draw_declaration` and `_draw_school` functions.

- Units are PDF points: A4 is 595 × 842, **origin bottom-left** (y grows upwards).
- `_Writer.text(x, y, value, width, size)` shrinks long text to fit `width`.
- `_Writer.lines(...)` word-wraps into a box.
- `_Writer.strike(...)` crosses out the wrong half of "Government Servant/NOT a Government Servant".
- Values are drawn in dark blue so they stand out from the print.

To re-measure, lay a grid over the pages and look at it:

```python
# run from backend/ with the venv python
import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
r = PdfReader("CEA-Application/CEA 2026.pdf"); w = PdfWriter()
for i in range(2, 7):
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(595.276, 841.89))
    c.setFont("Helvetica", 5)
    for x in range(0, 600, 25): c.line(x, 0, x, 842); c.drawString(x + 1, 2, str(x))
    for y in range(0, 850, 25): c.line(0, y, 596, y); c.drawString(2, y + 1, str(y))
    c.save(); buf.seek(0)
    page = w.add_page(r.pages[i]); page.merge_page(PdfReader(buf).pages[0])
w.write("grid.pdf")
```

Then render a test claim and check every page by eye before committing.
If the office issues a new version of the form, the positions will need
re-measuring.

---

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_cea.py              # the rules, no database
.venv\Scripts\python.exe -m pytest tests/test_api_dashboard_cea.py # API end to end (rolled back)
```

`test_api_dashboard_cea.py` covers: dashboard tiles, adding a family (cleaning,
per-box errors, duplicates, missing phone), eligibility ordering, pre-fill,
saving only what changed, blanks never wiping, bad values saving nothing, and
the PDF page count.

`test_supporting_and_table.py` covers: the 1–4 limits, file types, the blob
storage placeholder, documents added after the form pages (PDF and photo),
broken files leaving a note, the CEA PDF with documents, and the table
(paging, filters, search, cleaning, history, refusals, unchanged values).

---

## Open questions

- **₹2,813 vs ₹2,812.** The PDF says ₹2,813/month from Jan 2024; the poster
  says ₹2,812 from 2023-24. The PDF is used. Confirm with the office.
- **Academic year start.** Assumed April–March. The circular mentions
  "July 17 onwards". Change `academic_year_start_month` if needed.
- **Cause of death.** The circular covers all death-in-harness cases, so the
  engine does not filter by cause. Confirm whether any cases are excluded.
- **Mock data.** The seed leaves school name and record office empty (as
  agreed), so most claims show those as "still empty", and some seeded
  children have a class that does not fit their age (they show as "details missing").
