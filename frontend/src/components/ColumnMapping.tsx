"use client";

/**
 * Step 2 of an upload: how the sheet's columns were matched.
 *
 * His sheet always has the same fixed columns, so the matching is automatic
 * and this screen is read-only: he can see it, not change it. He is asked
 * only about a column the system does not know (add it or leave it out), and
 * a sheet without a required column (soldier's name, NOK name) cannot go on.
 */

import { useMemo, useState } from "react";
import {
  EXTRA_PREFIX,
  IGNORE,
  confirmMapping,
  createCustomField,
  type TargetField,
  type UploadResult,
} from "@/lib/api";

type Props = {
  result: UploadResult;
  onConfirmed: (mapping: Record<string, string>) => void;
  /** The choices confirmed earlier, when he comes back to this step with "Back". */
  saved?: Record<string, string> | null;
};

export default function ColumnMapping({ result, onConfirmed, saved }: Props) {
  // Start from what the system worked out (or what he confirmed before going
  // back); he corrects only if it is wrong.
  const [choices] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const column of result.columns) {
      initial[column.source_heading] =
        saved?.[column.source_heading] ?? column.target_key ?? "";
    }
    return initial;
  });
  // Extra fields added during this session, so the picker offers them too.
  const [extraFields, setExtraFields] = useState<TargetField[]>([]);
  const [showRecognised, setShowRecognised] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const options = useMemo(
    () => [...result.target_fields, ...extraFields],
    [result.target_fields, extraFields],
  );

  const labelFor = (key: string) =>
    options.find((o) => o.key === key)?.label ?? key;

  // --- how each column currently stands ---
  const recognised = result.columns.filter((c) => {
    const value = choices[c.source_heading];
    return value && value !== IGNORE && !value.startsWith(EXTRA_PREFIX);
  });
  const asExtra = result.columns.filter((c) =>
    choices[c.source_heading]?.startsWith(EXTRA_PREFIX),
  );
  // Columns the system proposes storing as new fields. Nothing is created
  // until he presses the confirm button.
  const proposed = result.columns.filter(
    (c) => !choices[c.source_heading] && c.suggested_new_field,
  );
  const unknown = result.columns.filter(
    (c) => !choices[c.source_heading] && !c.suggested_new_field,
  );
  const ignored = result.columns.filter(
    (c) => choices[c.source_heading] === IGNORE,
  );

  // Columns we have no home for: he decides, one by one, to keep each as new
  // information or leave it out. Suggested ones start as "keep"; ones we could
  // not make sense of start as "leave out", so junk like "S.No" stays out.
  const [extraDecision, setExtraDecision] = useState<Record<string, "add" | "ignore">>(() => {
    const initial: Record<string, "add" | "ignore"> = {};
    for (const column of result.columns) {
      if (!column.target_key) {
        const before = saved?.[column.source_heading];
        initial[column.source_heading] =
          before === IGNORE ? "ignore" : column.suggested_new_field ? "add" : "ignore";
      }
    }
    return initial;
  });
  // Only columns the system doesn't know are asked about. Ones it skips by
  // itself (S NO, DOCUMENTS 1-4) or that he left out before are just listed.
  const extras = [...proposed, ...unknown];

  // Fields we keep that this sheet has no column for. They stay empty for
  // these families (nothing already stored is wiped).
  const notInSheet = result.target_fields.filter(
    (f) => !f.key.startsWith(EXTRA_PREFIX) && !Object.values(choices).includes(f.key),
  );
  const [showNotInSheet, setShowNotInSheet] = useState(false);

  const missingRequired = options.filter(
    (f) => f.required && !Object.values(choices).includes(f.key),
  );
  const canConfirm = missingRequired.length === 0 && !saving && !done;

  async function addField(heading: string, label: string): Promise<string> {
    const created = await createCustomField(label, heading, result.import_id);
    const key = `${EXTRA_PREFIX}${created.key}`;
    setExtraFields((prev) =>
      prev.some((f) => f.key === key)
        ? prev
        : [
            ...prev,
            {
              key,
              label: created.label,
              group: "Extra information",
              required: false,
            },
          ],
    );
    return key;
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      // Create the new fields he chose to keep, now that he has agreed.
      const created: Record<string, string> = {};
      for (const column of extras) {
        if (extraDecision[column.source_heading] !== "add") continue;
        created[column.source_heading] = await addField(
          column.source_heading,
          column.suggested_new_field ?? column.source_heading,
        );
      }

      const toSend: Record<string, string> = {};
      for (const [heading, target] of Object.entries(choices)) {
        toSend[heading] = created[heading] ?? (target || IGNORE);
      }
      for (const [heading, key] of Object.entries(created)) {
        toSend[heading] = key;
      }
      await confirmMapping(result.import_id, toSend);
      setDone(true);
      onConfirmed(toSend);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the mapping.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
      <h2 className="text-[18px] font-semibold">What is in each column?</h2>
      <p className="mt-1 text-[15px] leading-relaxed text-muted">
        I read <span className="font-medium text-text">{result.filename}</span> — sheet
        &ldquo;{result.sheet_name}&rdquo;, headings on row {result.header_row_number},{" "}
        <span className="font-medium text-text">{result.row_count} rows</span>.
      </p>

      {/* ---------- a short summary ---------- */}
      <div className="mt-4 space-y-4">
        <div>
          <button
            onClick={() => setShowRecognised((v) => !v)}
            className="flex min-h-12 w-full items-center justify-between gap-3 rounded-lg bg-surface-2
              px-3 py-2.5 text-left"
          >
            <span className="text-[15px] font-medium">
              {recognised.length} columns I recognised
            </span>
            <span className="text-xs text-muted">
              {showRecognised ? "hide" : "show"}
            </span>
          </button>
          {showRecognised && (
            <ul className="mt-1">
              {recognised.map((column) => (
                <li
                  key={column.source_heading}
                  className="flex gap-2 border-t border-border px-1 py-1.5 text-[15px]"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {column.source_heading}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {asExtra.length > 0 && (
          <div className="rounded-lg border border-border px-3 py-2.5">
            <p className="text-[15px] font-medium">Stored as extra information</p>
            <ul className="mt-1 space-y-0.5">
              {asExtra.map((column) => (
                <li key={column.source_heading} className="text-[15px]">
                  {column.source_heading}
                  <span className="text-muted"> → {labelFor(choices[column.source_heading])}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {extras.length > 0 && (
          <div className="rounded-xl border border-accent bg-accent-soft px-4 py-3">
            <p className="text-[16px] font-semibold">
              {extras.length} extra column{extras.length === 1 ? "" : "s"} in your sheet
            </p>
            <p className="mt-0.5 text-[15px] text-muted">
              The database has no place for {extras.length === 1 ? "this" : "these"} yet.
              Choose for each one: add it as new information, or leave it out.
            </p>
            <ul className="mt-3 space-y-2">
              {extras.map((column) => {
                const decision = extraDecision[column.source_heading] ?? "ignore";
                const decide = (d: "add" | "ignore") => {
                  setExtraDecision((prev) => ({ ...prev, [column.source_heading]: d }));
                };
                return (
                  <li
                    key={column.source_heading}
                    className="flex flex-col gap-2 rounded-lg bg-bg px-3 py-2.5 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[16px] font-medium">{column.source_heading}</p>
                      {column.samples.length > 0 && (
                        <p className="truncate text-[13px] text-muted">
                          e.g. {column.samples.slice(0, 3).join(", ")}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-1.5 sm:shrink-0" role="group" aria-label={column.source_heading}>
                      {(["add", "ignore"] as const).map((d) => (
                        <button
                          key={d}
                          type="button"
                          aria-pressed={decision === d}
                          onClick={() => decide(d)}
                          className={`min-h-11 flex-1 rounded-full border px-4 py-2 text-[15px] transition sm:flex-none ${
                            decision === d
                              ? d === "add"
                                ? "border-accent bg-accent font-semibold text-accent-fg"
                                : "border-text bg-text font-semibold text-bg"
                              : "border-border bg-bg text-muted hover:bg-surface-2"
                          }`}
                        >
                          {d === "add" ? "Add to database" : "Leave out"}
                        </button>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {ignored.length > 0 && (
          <p className="text-[15px] text-muted">
            <span className="font-medium text-text">Not imported:</span>{" "}
            {ignored.map((c) => c.source_heading).join(", ")}
          </p>
        )}

        {notInSheet.length > 0 && (
          <div className="rounded-xl border border-border px-4 py-3">
            <button
              type="button"
              onClick={() => setShowNotInSheet((v) => !v)}
              aria-expanded={showNotInSheet}
              className="flex w-full items-center justify-between gap-3 text-left"
            >
              <span>
                <span className="block text-[16px] font-semibold">
                  {notInSheet.length} field{notInSheet.length === 1 ? "" : "s"} missing from your sheet
                </span>
                <span className="block text-[15px] text-muted">
                  These stay empty for new families. Anything already stored is kept.
                  You can still add one, with a value for every row, on the next step.
                </span>
              </span>
              <span className="shrink-0 text-[15px] text-accent underline">
                {showNotInSheet ? "Hide" : "Show"}
              </span>
            </button>
            {showNotInSheet && (
              <ul className="mt-3 flex flex-wrap gap-1.5">
                {notInSheet.map((f) => (
                  <li key={f.key} className="rounded-full bg-surface-2 px-3 py-1 text-[14px]">
                    {f.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* ---------- actions ---------- */}
      <div className="mt-5 space-y-2 border-t border-border pt-4">
        {missingRequired.length > 0 && (
          <p className="text-[15px] text-danger">
            This sheet has no column for {missingRequired.map((f) => f.label).join(" or ")}, so it
            cannot be imported. Check that it is the right sheet.
          </p>
        )}
        {error && <p className="text-[15px] text-danger">{error}</p>}

        {done ? (
          <p className="text-[15px] font-medium text-accent">
            Saved. I will remember this layout next time.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={save}
              disabled={!canConfirm}
              className="w-full rounded-full bg-accent px-6 py-3 text-[17px] font-semibold sm:w-auto
                text-accent-fg disabled:cursor-not-allowed disabled:bg-surface-2
                disabled:text-muted"
            >
              {saving ? "Saving..." : "Yes, that's correct"}
            </button>
          </div>
        )}
      </div>

      <p className="mt-3 text-xs text-muted">
        Nothing has been saved to the family records yet.
      </p>
    </div>
  );
}
