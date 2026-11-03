"use client";

import { useMemo, useState } from "react";
import FieldPicker from "@/components/FieldPicker";
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
};

export default function ColumnMapping({ result, onConfirmed }: Props) {
  // Start from what the system worked out; he corrects only if it is wrong.
  const [choices, setChoices] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const column of result.columns) {
      initial[column.source_heading] = column.target_key ?? "";
    }
    return initial;
  });
  // Extra fields added during this session, so the picker offers them too.
  const [extraFields, setExtraFields] = useState<TargetField[]>([]);
  const [editing, setEditing] = useState(false);
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

  const missingRequired = options.filter(
    (f) => f.required && !Object.values(choices).includes(f.key),
  );
  const duplicates = useMemo(() => {
    const seen = new Set<string>();
    const clashes = new Set<string>();
    for (const target of Object.values(choices)) {
      if (!target || target === IGNORE) continue;
      if (seen.has(target)) clashes.add(target);
      seen.add(target);
    }
    return clashes;
  }, [choices]);

  const canConfirm =
    missingRequired.length === 0 && duplicates.size === 0 && !saving && !done;

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
      // Create the proposed new fields now that he has agreed to them.
      const created: Record<string, string> = {};
      for (const column of proposed) {
        created[column.source_heading] = await addField(
          column.source_heading,
          column.suggested_new_field as string,
        );
      }

      const toSend: Record<string, string> = {};
      for (const [heading, target] of Object.entries(choices)) {
        toSend[heading] = created[heading] ?? target ?? IGNORE;
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
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h2 className="text-[17px] font-semibold">What is in each column?</h2>
      <p className="mt-1 text-[15px] leading-relaxed text-muted">
        I read <span className="font-medium text-text">{result.filename}</span> — sheet
        &ldquo;{result.sheet_name}&rdquo;, headings on row {result.header_row_number},{" "}
        <span className="font-medium text-text">{result.row_count} rows</span>.
      </p>

      {result.remembered && (
        <p className="mt-3 rounded-lg bg-accent-soft px-3 py-2 text-[15px]">
          I recognised this sheet from last time and filled it in the same way.
        </p>
      )}

      {/* ---------- the normal view: a short summary ---------- */}
      {!editing && (
        <div className="mt-4 space-y-4">
          <div>
            <button
              onClick={() => setShowRecognised((v) => !v)}
              className="flex w-full items-center justify-between rounded-lg bg-surface-2
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
                    <span className="text-muted" aria-hidden="true">
                      →
                    </span>
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {labelFor(choices[column.source_heading])}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {(proposed.length > 0 || asExtra.length > 0) && (
            <div className="rounded-lg border border-accent bg-accent-soft px-3 py-2.5">
              <p className="text-[15px] font-medium">
                {proposed.length + asExtra.length} column
                {proposed.length + asExtra.length === 1 ? "" : "s"} are new to me
              </p>
              <ul className="mt-1 space-y-0.5">
                {proposed.map((column) => (
                  <li key={column.source_heading} className="text-[15px]">
                    {column.source_heading}
                    {column.suggested_new_field !== column.source_heading && (
                      <span className="text-muted">
                        {" "}
                        → store as &ldquo;{column.suggested_new_field}&rdquo;
                      </span>
                    )}
                  </li>
                ))}
                {asExtra.map((column) => (
                  <li key={column.source_heading} className="text-[15px]">
                    {column.source_heading}
                    <span className="text-muted"> → {labelFor(choices[column.source_heading])}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-[14px] text-muted">
                I will store these as new information against each family.
              </p>
            </div>
          )}

          {unknown.length > 0 && (
            <div className="rounded-lg border border-warning px-3 py-2.5">
              <p className="text-[15px] font-medium text-warning">
                {unknown.length} column{unknown.length === 1 ? "" : "s"} I could not
                work out
              </p>
              <ul className="mt-1 space-y-0.5">
                {unknown.map((column) => (
                  <li key={column.source_heading} className="text-[15px]">
                    {column.source_heading}
                  </li>
                ))}
              </ul>
              <p className="mt-1.5 text-[14px] text-muted">
                These will be skipped unless you tell me what they are.
              </p>
            </div>
          )}

          {ignored.length > 0 && (
            <p className="text-[14px] text-muted">
              Not importing: {ignored.map((c) => c.source_heading).join(", ")}
            </p>
          )}
        </div>
      )}

      {/* ---------- the editing view ---------- */}
      {editing && (
        <ul className="mt-4 space-y-3">
          {result.columns.map((column) => {
            const value = choices[column.source_heading] ?? "";
            return (
              <li
                key={column.source_heading}
                className="grid gap-2 border-t border-border pt-3 sm:grid-cols-2 sm:gap-4"
              >
                <div className="min-w-0">
                  <p className="text-[15px] font-medium">{column.source_heading}</p>
                  {column.samples.length > 0 && (
                    <p
                      className="truncate text-xs text-muted"
                      title={column.samples.join(", ")}
                    >
                      e.g. {column.samples.slice(0, 3).join(", ")}
                    </p>
                  )}
                </div>
                <div>
                  <FieldPicker
                    value={value}
                    options={options}
                    heading={column.suggested_new_field ?? column.source_heading}
                    proposedLabel={column.suggested_new_field}
                    invalid={Boolean(value) && duplicates.has(value)}
                    onChange={(next) =>
                      setChoices((prev) => ({
                        ...prev,
                        [column.source_heading]: next,
                      }))
                    }
                    onCreateField={(label) =>
                      addField(column.source_heading, label)
                    }
                  />
                  <p className="mt-1 text-xs text-muted">{column.reason}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* ---------- actions ---------- */}
      <div className="mt-5 space-y-2 border-t border-border pt-4">
        {missingRequired.length > 0 && (
          <p className="text-[15px] text-danger">
            Still needed: {missingRequired.map((f) => f.label).join(", ")}.
            {!editing && " Use “Edit columns” to set them."}
          </p>
        )}
        {duplicates.size > 0 && (
          <p className="text-[15px] text-danger">
            Two columns are set to the same field. Please pick one.
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
              className="rounded-full bg-accent px-5 py-2.5 text-[15px] font-medium
                text-accent-fg disabled:cursor-not-allowed disabled:bg-surface-2
                disabled:text-muted"
            >
              {saving ? "Saving..." : "Yes, that's correct"}
            </button>
            <button
              onClick={() => setEditing((v) => !v)}
              className="text-[15px] text-accent underline"
            >
              {editing ? "Back to the summary" : "Edit columns"}
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
