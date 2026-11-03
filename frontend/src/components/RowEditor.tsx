"use client";

import { useState } from "react";
import { editImportRow, type PreviewResult, type RowPreview } from "@/lib/api";

type Props = {
  importId: number;
  row: RowPreview;
  onUpdated: (preview: PreviewResult) => void;
  onClose: () => void;
};

/** Correct one row, or leave it out, before anything is saved. */
export default function RowEditor({ importId, row, onUpdated, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of row.fields) initial[field.field_key] = field.value;
    return initial;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(body: { values?: Record<string, string>; skip?: boolean }) {
    setSaving(true);
    setError(null);
    try {
      onUpdated(await editImportRow(importId, row.row_number, body));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that change.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  /** Send what he altered, plus corrections he made earlier. */
  async function save() {
    const changed: Record<string, string> = {};
    for (const field of row.fields) {
      if (values[field.field_key] !== field.value || field.edited) {
        changed[field.field_key] = values[field.field_key] ?? "";
      }
    }
    if (await send({ values: changed, skip: row.skipped_by_user })) {
      onClose();
    }
  }

  return (
    <div className="mt-2 rounded-lg border border-border bg-bg p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {row.fields.map((field) => (
          <label key={field.field_key} className="block">
            <span className="block text-xs text-muted">
              {field.label}
              {field.edited && (
                <span className="ml-1 text-accent">you changed this</span>
              )}
            </span>
            <input
              value={values[field.field_key] ?? ""}
              onChange={(e) =>
                setValues((prev) => ({
                  ...prev,
                  [field.field_key]: e.target.value,
                }))
              }
              className="mt-0.5 w-full rounded-lg border border-border bg-bg px-3 py-2.5
                text-[16px] outline-none focus:border-accent"
            />
          </label>
        ))}
      </div>

      {error && <p className="mt-2 text-[14px] text-danger">{error}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="min-h-11 rounded-full bg-accent px-5 text-[16px] font-semibold
            text-accent-fg disabled:bg-surface-2 disabled:text-muted"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          onClick={onClose}
          disabled={saving}
          className="min-h-11 px-2 text-[16px] text-muted underline"
        >
          Cancel
        </button>
        <button
          onClick={() => send({ values: {}, skip: !row.skipped_by_user })}
          disabled={saving}
          className="min-h-11 text-[15px] text-warning underline sm:ml-auto"
        >
          {row.skipped_by_user ? "Put this row back" : "Leave this row out"}
        </button>
      </div>

      <p className="mt-2 text-xs text-muted">
        Your Excel file is not changed. These corrections apply to this import only.
      </p>
    </div>
  );
}
