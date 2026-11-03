"use client";

import { useState } from "react";
import {
  EXTRA_PREFIX,
  editImportColumns,
  retireCustomField,
  type PreviewResult,
} from "@/lib/api";

type Props = {
  preview: PreviewResult;
  onUpdated: (preview: PreviewResult) => void;
};

/**
 * The columns this import will write. Remove one, or add a field his sheet
 * doesn't have (with an optional value for every row).
 */
export default function PreviewColumns({ preview, onUpdated }: Props) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(body: Parameters<typeof editImportColumns>[1]) {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await editImportColumns(preview.import_id, body));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the columns.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function addColumn() {
    if (!newKey) return;
    if (await change({ add_fields: { [newKey]: newValue } })) {
      setAdding(false);
      setNewKey("");
      setNewValue("");
    }
  }

  async function deleteExtraField(key: string, label: string) {
    const ok = window.confirm(
      `Stop offering "${label}" as an extra field? Values already saved are kept.`,
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      await retireCustomField(key.slice(EXTRA_PREFIX.length));
      // Refresh so the picker no longer lists it.
      onUpdated(await editImportColumns(preview.import_id, {}));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove that field.");
    } finally {
      setBusy(false);
    }
  }

  const columns = preview.active_columns;
  const extraChoices = preview.addable_fields.filter((f) =>
    f.key.startsWith(EXTRA_PREFIX),
  );

  return (
    <div className="mt-4 rounded-lg border border-border">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-12 w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
      >
        <span className="text-[15px] font-medium">
          {columns.length} columns will be imported
        </span>
        <span className="text-xs text-muted">{open ? "hide" : "add or remove"}</span>
      </button>

      {open && (
        <div className="border-t border-border px-3 py-3">
          <ul className="flex flex-wrap gap-2">
            {columns.map((column) => (
              <li
                key={column.field_key}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[14px] ${
                  column.added ? "border-accent bg-accent-soft" : "border-border bg-bg"
                }`}
                title={
                  column.added
                    ? "Added by you"
                    : `From the column "${column.source_heading}"`
                }
              >
                <span>{column.label}</span>
                {column.added && column.default_value && (
                  <span className="text-xs text-muted">= {column.default_value}</span>
                )}
                {!column.required && (
                  <button
                    onClick={() =>
                      change(
                        column.added
                          ? { remove_added: [column.field_key] }
                          : { remove_headings: [column.source_heading as string] },
                      )
                    }
                    disabled={busy}
                    title="Skip this column for this Excel only"
                    className="ml-1 min-h-8 rounded-full border border-border px-2.5 text-[13px]
                      text-muted hover:border-text hover:text-text"
                  >
                    Don&rsquo;t import
                  </button>
                )}
              </li>
            ))}
          </ul>

          {adding ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <select
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                className="rounded-lg border border-border bg-bg px-3 py-2 text-[15px]"
              >
                <option value="">Choose a field to add...</option>
                {preview.addable_fields.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label} ({field.group})
                  </option>
                ))}
              </select>
              <input
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Same value for every row (optional)"
                className="rounded-lg border border-border bg-bg px-3 py-2 text-[15px]"
              />
              <div className="flex gap-2">
                <button
                  onClick={addColumn}
                  disabled={!newKey || busy}
                  className="min-h-11 flex-1 rounded-full bg-accent px-5 text-[16px] font-semibold
                    text-accent-fg disabled:bg-surface-2 disabled:text-muted sm:flex-none"
                >
                  Add
                </button>
                <button
                  onClick={() => setAdding(false)}
                  className="min-h-11 px-3 text-[16px] text-muted underline"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="mt-2 min-h-11 text-left text-[15px] text-accent underline"
            >
              + Add a column that isn&rsquo;t in the sheet
            </button>
          )}

          <p className="mt-2 text-xs text-muted">
            Removing a column only stops it being imported; your Excel file is not
            changed. For an added column, fill individual rows with <em>edit</em>.
          </p>

          {extraChoices.length > 0 && (
            <div className="mt-3 border-t border-border pt-2">
              <p className="text-xs text-muted">
                Extra fields added earlier. Deleting one stops it being offered for
                all future Excels; values already saved are kept.
              </p>
              <ul className="mt-1 flex flex-wrap gap-2">
                {extraChoices.map((field) => (
                  <li
                    key={field.key}
                    className="flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-[13px]"
                  >
                    {field.label}
                    <button
                      onClick={() => deleteExtraField(field.key, field.label)}
                      disabled={busy}
                      title="Stop offering this field for all future Excels"
                      className="ml-1 rounded-full border border-danger px-2 text-xs
                        text-danger hover:bg-danger hover:text-bg"
                    >
                      Delete field
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {error && <p className="mt-2 text-[14px] text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
