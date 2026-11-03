# New flow (agreed 2026-10-30)

Replaces the earlier grant form-filling plan. Development has not started.

## Decisions

**Excel**
- `LIST OF FIELDS` sheet (42 fields) in `LIST OF FIELDS.xlsx` is the **final field list**.
- Fields only in the `SAMPLE DATA` sheet are left out (listed in `grants-open-questions.md` discussion; to be given to the user).
- Fields the **CEA form** needs that aren't in the 42 are **added to the database**, with **empty** mock values for now.
- In the preview he can change values (fill, fix, clear), leave rows out, and **add or remove whole columns**.
- Children arrive as side-by-side columns (Child1/2/3) and are split into separate child records.

**Documents**
- He picks a family **or a specific child**, then uploads documents linked to them.

**Eligibility**
- Worked out from the posters. **CEA only** for now. Formula to be discussed.

**Forms**
- He picks or uploads the **CEA** form → eligible families are suggested → he filters/edits the list
  → each family's form appears as **editable fields**, pre-filled from the database → then PDF.
- Edits on the form **update the family's record** (old value kept in history).

**Voice**
- Follows the same pattern as Excel.

## How it connects

```
┌──────────────────────────────────────────────────────────────┐
│                         INPUTS                               │
│     Excel upload         Voice note          Documents       │
└──────┬─────────────────────┬────────────────────┬────────────┘
       ▼                     ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌────────────────┐
│ Column check │     │  Transcript  │     │ Pick family or │
│ + Preview    │     │  + proposed  │     │ child, attach  │
│ (edit, skip, │     │  changes     │     │ files          │
│ add/remove   │     │  (confirm)   │     │                │
│ columns)     │     │              │     │                │
└──────┬───────┘     └──────┬───────┘     └───────┬────────┘
       └────────────────────┼─────────────────────┘
                            ▼
              ┌───────────────────────────┐
              │         DATABASE          │
              │  His 42 fields + CEA      │
              │  fields, children,        │
              │  documents, history       │
              └─────────────┬─────────────┘
                            ▼
              ┌───────────────────────────┐
              │   ELIGIBILITY (CEA only)  │
              └─────────────┬─────────────┘
                            ▼
              ┌───────────────────────────┐
              │      CEA FORM FILLING     │
              │  suggest → filter → edit  │
              │  → PDF                    │
              └───────────────────────────┘
```

## Excel upload

```
Drop Excel → Read sheet → Match columns (rules → Gemini → new field)
  → Column screen (confirm / edit columns)
  → Preview: edit/fill/clear values ✅, leave row out ✅,
             add column 🆕, remove column 🆕
  → Import (history kept; Child1/2/3 → separate children 🆕)
```

## CEA form filling

```
Pick/upload CEA form → eligibility → suggested families
  → filter / add / remove → editable form per family (pre-filled)
  → edits saved back to the record → PDF
```

## Built vs new

| Part | Status |
|---|---|
| Excel: column matching, preview, edit/skip rows, import, history | built |
| Voice: transcript, suggested family, proposed changes | built |
| Switch to the 42 fields + CEA fields | new |
| Children columns → separate child records | new |
| Add/remove columns in the preview | new |
| Documents linked to family or child | new |
| CEA eligibility | new (formula to discuss) |
| CEA form: suggest → filter → edit → PDF | new |
| Voice following the new pattern | new |
