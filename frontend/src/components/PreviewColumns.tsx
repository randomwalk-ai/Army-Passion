"use client";

import { useState } from "react";
import {
  EXTRA_PREFIX,
  createCustomField,
  editImportColumns,
  type PreviewResult,
} from "@/lib/api";

/** The dropdown choice that opens the "name of the new field" box. */
const NEW_FIELD = "__new_field__";

const sameName = (a: string, b: string) =>
  a.toLowerCase().replace(/[^a-z0-9]/g, "") === b.toLowerCase().replace(/[^a-z0-9]/g, "");

type Props = {
  preview: PreviewResult;
  onUpdated: (preview: PreviewResult) => void;
};

/**
 * The columns this import will write. Remove one, or add a field his sheet
 * doesn't have (with an optional value for every row) — an existing one, or
 * a brand-new one he names himself ("Door No").
 */
export default function PreviewColumns({ preview, onUpdated }: Props) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newName, setNewName] = useState("");
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

  /** The field to add: the one picked, or a new one made from the typed name. */
  async function fieldToAdd(): Promise<string | null> {
    if (newKey !== NEW_FIELD) return newKey;
    const name = newName.trim();
    if (name.length < 2) {
      setError("Type a name for the new field.");
      return null;
    }
    // A name that already exists is reused, never made twice.
    const existing = preview.addable_fields.find((f) => sameName(f.label, name));
    if (existing) return existing.key;
    if (preview.active_columns.some((c) => sameName(c.label, name))) {
      setError(`“${name}” is already in this sheet.`);
      return null;
    }
    const created = await createCustomField(name, undefined, preview.import_id);
    return `${EXTRA_PREFIX}${created.key}`;
  }

  async function addColumn() {
    if (!newKey) return;
    setError(null);
    let key: string | null;
    try {
      key = await fieldToAdd();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create that field.");
      return;
    }
    if (!key) return;
    if (await change({ add_fields: { [key]: newValue } })) {
      setAdding(false);
      setNewKey("");
      setNewName("");
      setNewValue("");
    }
  }

  const columns = preview.active_columns;
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
                {column.required ? (
                  <span
                    title="Every family needs this, so it is always imported"
                    className="ml-1 rounded-full bg-text px-2.5 py-0.5 text-[13px] font-medium text-bg"
                  >
                    Required
                  </span>
                ) : (
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
            <div className={`mt-3 grid gap-2 ${newKey === NEW_FIELD ? "sm:grid-cols-[1fr_1fr_1fr_auto]" : "sm:grid-cols-[1fr_1fr_auto]"}`}>
              <select
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                className="rounded-lg border border-border bg-bg px-3 py-2 text-[15px]"
              >
                <option value="">Choose a field to add...</option>
                <option value={NEW_FIELD}>+ Create a new field</option>
                {preview.addable_fields.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label} ({field.group})
                  </option>
                ))}
              </select>
              {newKey === NEW_FIELD && (
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Name of the new field, e.g. Door No"
                  aria-label="Name of the new field"
                  autoFocus
                  maxLength={160}
                  className="rounded-lg border border-accent bg-bg px-3 py-2 text-[15px]"
                />
              )}
              <input
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Same value for every row (optional)"
                className="rounded-lg border border-border bg-bg px-3 py-2 text-[15px]"
              />
              <div className="flex gap-2">
                <button
                  onClick={addColumn}
                  disabled={!newKey || (newKey === NEW_FIELD && newName.trim().length < 2) || busy}
                  className="min-h-11 flex-1 rounded-full bg-accent px-5 text-[16px] font-semibold
                    text-accent-fg disabled:bg-surface-2 disabled:text-muted sm:flex-none"
                >
                  Add
                </button>
                <button
                  onClick={() => {
                    setAdding(false);
                    setNewKey("");
                    setNewName("");
                    setError(null);
                  }}
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

          {error && <p className="mt-2 text-[14px] text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
