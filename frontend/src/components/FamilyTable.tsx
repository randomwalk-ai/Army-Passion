"use client";

/**
 * Every family as one table, like his Excel sheet: read it, search it, sort
 * it, and (with Editing switched on) correct a value in place.
 *
 * On a computer he clicks a box and types. On a phone the table scrolls
 * sideways with the name pinned on the left, and tapping a name opens the
 * whole family as a list that is easier to edit with a thumb. Every change
 * goes through the server's checks, and the old value is kept in history.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import EligibilityBadge from "@/components/EligibilityBadge";
import FamilyEligibility from "@/components/FamilyEligibility";
import { SupportingDocuments, MAX_DOCUMENTS } from "@/components/SupportingDocuments";
import { Notice, buttonSecondary, errorText, formatDateTyping } from "@/components/ui";
import {
  editFamilyCell,
  getFamiliesTable,
  getFamilyRow,
  type FamiliesTable,
  type TableColumn,
  type TableRow,
} from "@/lib/api";

type Value = string | number | null;
type CellRef = { familyId: number; key: string };

const NAME = "primary_contact_name";

// --- showing values -------------------------------------------------------

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "+919876543210" -> "+91 98765 43210" */
function formatPhone(phone: string): string {
  const m = /^\+91(\d{5})(\d{5})$/.exec(phone);
  return m ? `+91 ${m[1]} ${m[2]}` : phone;
}

function display(column: TableColumn, value: Value): string {
  if (value === null || value === "") return "";
  if (column.key === "documents") return `${value} of ${MAX_DOCUMENTS}`;
  if (column.kind === "phone") return formatPhone(String(value));
  if (column.kind === "choice") return capitalise(String(value));
  return String(value);
}

/** What goes in the box when he starts editing. */
function editable(column: TableColumn, value: Value): string {
  if (value === null) return "";
  if (column.kind === "phone") return formatPhone(String(value));
  return String(value);
}

const WIDTH: Record<string, string> = {
  [NAME]: "min-w-[9.5rem] max-w-[11rem] sm:min-w-[13rem] sm:max-w-[16rem]",
  family_code: "min-w-[8rem]",
  documents: "min-w-[7rem]",
  children: "min-w-[6rem]",
  unit: "min-w-[11rem]",
  email: "min-w-[15rem]",
  bank_name: "min-w-[11rem]",
};

// --- the editor used in a table box and in the family panel ----------------

function CellEditor({
  column,
  initial,
  onSave,
  onCancel,
  onTab,
  large,
}: {
  column: TableColumn;
  initial: string;
  /** Resolves to an error message, or null when saved. */
  onSave: (value: string) => Promise<string | null>;
  onCancel: () => void;
  onTab?: (backwards: boolean) => void;
  large?: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastTried = useRef<string | null>(null);
  const ref = useRef<HTMLInputElement & HTMLSelectElement>(null);

  useEffect(() => {
    ref.current?.focus();
    if (ref.current && "select" in ref.current && column.kind !== "choice") ref.current.select();
  }, [column.kind]);

  async function commit(then?: () => void) {
    if (saving) return;
    if (draft.trim() === initial.trim()) {
      (then ?? onCancel)();
      return;
    }
    // Leaving the box again with the same refused value should not ask twice.
    if (lastTried.current === draft && error) return;
    lastTried.current = draft;
    setSaving(true);
    const problem = await onSave(draft);
    setSaving(false);
    setError(problem);
    if (!problem) then?.();
  }

  const base = `w-full rounded-lg border bg-bg outline-none focus:border-accent ${
    error ? "border-danger" : "border-accent"
  } ${large ? "min-h-12 px-3 text-[17px]" : "min-h-10 px-2.5 text-[16px]"}`;

  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    } else if (e.key === "Tab" && onTab) {
      e.preventDefault();
      commit(() => onTab(e.shiftKey));
    }
  };

  return (
    <div className="relative">
      {column.kind === "choice" ? (
        <select
          ref={ref}
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={keys}
          onBlur={() => !large && commit()}
          aria-label={column.label}
          className={base}
        >
          {!column.required && <option value="">(blank)</option>}
          {column.choices.map((c) => (
            <option key={c} value={c}>
              {capitalise(c)}
            </option>
          ))}
        </select>
      ) : (
        <input
          ref={ref}
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(column.kind === "date" ? formatDateTyping(e.target.value) : e.target.value)}
          onKeyDown={keys}
          onBlur={() => !large && commit()}
          aria-label={column.label}
          aria-invalid={error ? true : undefined}
          inputMode={column.kind === "phone" ? "tel" : column.kind === "date" || column.kind === "number" ? "numeric" : undefined}
          placeholder={column.kind === "date" ? "DD-MM-YYYY" : column.required ? "Needed" : ""}
          autoComplete="off"
          className={base}
        />
      )}
      {saving && <p className="mt-1 text-[13px] text-muted">Saving…</p>}
      {error && <p className="mt-1 whitespace-normal text-[14px] leading-snug text-danger">{error}</p>}
      {large && (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => commit()}
            disabled={saving}
            className="min-h-11 rounded-full bg-accent px-5 text-[16px] font-semibold text-accent-fg disabled:bg-surface-2 disabled:text-muted"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <button type="button" onClick={onCancel} className="min-h-11 px-3 text-[16px] text-muted underline">
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

// --- the family, as a list (opens from a name) ----------------------------

function FamilyPanel({
  row,
  columns,
  editing,
  onSave,
  onDocuments,
  onClose,
}: {
  row: TableRow;
  columns: TableColumn[];
  editing: boolean;
  onSave: (key: string, value: string) => Promise<string | null>;
  onDocuments: (count: number) => void;
  onClose: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !open && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  const shown = columns.filter((c) => c.key !== NAME && c.key !== "documents" && c.kind !== "status");

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={String(row.values[NAME] ?? "Family")}>
      <button aria-label="Close" onClick={onClose} className="absolute inset-0 bg-black/40" tabIndex={-1} />
      <div
        className="pb-safe absolute inset-x-0 bottom-0 flex max-h-[92dvh] flex-col rounded-t-3xl border border-border bg-bg shadow-2xl
          sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[30rem] sm:rounded-none sm:border-y-0 sm:border-r-0"
      >
        <div className="flex items-start gap-3 border-b border-border px-4 pb-3 pt-4 sm:px-6 sm:pt-6">
          <div className="min-w-0 flex-1">
            <p className="text-[14px] text-muted">{row.values.family_code}</p>
            <h2 className="text-[22px] font-semibold leading-tight">{row.values[NAME]}</h2>
            {row.values.soldier_name && (
              <p className="text-[15px] text-muted">
                {row.values.nok_relationship ? `${row.values.nok_relationship} of ` : "Family of "}
                {row.values.soldier_rank ? `${row.values.soldier_rank} ` : ""}
                {row.values.soldier_name}
              </p>
            )}
          </div>
          <button
            ref={closeButton}
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-text"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6">
          <div className="mb-4 flex flex-wrap gap-2">
            <Link href={`/cea/${row.family_id}`} className="inline-flex min-h-11 items-center rounded-full border border-border px-4 text-[15px] font-medium hover:bg-surface-2">
              CEA claim
            </Link>
          </div>

          <h3 className="mb-2 text-[17px] font-semibold">What they can claim</h3>
          <FamilyEligibility familyId={row.family_id} />

          <h3 className="mb-2 mt-7 text-[17px] font-semibold">Documents</h3>
          <SupportingDocuments familyId={row.family_id} onChange={(docs) => onDocuments(docs.length)} />

          <h3 className="mb-1 mt-7 text-[17px] font-semibold">Details</h3>
          {!editing && (
            <p className="mb-2 text-[14px] text-muted">Switch on Editing to change these.</p>
          )}
          <dl className="divide-y divide-border">
            {[columns.find((c) => c.key === NAME)!, ...shown].map((c) => (
              <div key={c.key} className="py-3">
                <dt className="text-[14px] text-muted">{c.label}</dt>
                {open === c.key ? (
                  <dd className="mt-1">
                    <CellEditor
                      large
                      column={c}
                      initial={editable(c, row.values[c.key])}
                      onCancel={() => setOpen(null)}
                      onSave={async (v) => {
                        const problem = await onSave(c.key, v);
                        if (!problem) setOpen(null);
                        return problem;
                      }}
                    />
                  </dd>
                ) : (
                  <dd className="flex items-center gap-2">
                    <span className={`min-w-0 flex-1 break-words text-[17px] ${display(c, row.values[c.key]) ? "" : "text-muted"}`}>
                      {display(c, row.values[c.key]) || "Not known"}
                    </span>
                    {editing && c.editable && (
                      <button
                        onClick={() => setOpen(c.key)}
                        className="min-h-11 shrink-0 rounded-full px-3 text-[15px] font-medium text-accent hover:bg-surface-2"
                      >
                        Change
                      </button>
                    )}
                  </dd>
                )}
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

// --- the table --------------------------------------------------------------

function EditSwitch({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`inline-flex min-h-11 shrink-0 items-center gap-2.5 rounded-full border px-4 text-[16px] font-medium transition ${
        on ? "border-accent bg-accent-soft" : "border-border bg-bg hover:bg-surface-2"
      }`}
    >
      <span className={`relative h-6 w-10 rounded-full transition ${on ? "bg-accent" : "bg-surface-2 ring-1 ring-inset ring-border"}`} aria-hidden="true">
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-bg shadow transition-all ${on ? "left-[1.125rem]" : "left-0.5"}`} />
      </span>
      Editing
    </button>
  );
}

function SortArrow({ direction }: { direction: "asc" | "desc" | null }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" className={direction ? "text-accent" : "text-muted opacity-50"}>
      {direction === "desc" ? (
        <path d="M12 5v14m0 0l-6-6m6 6l6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M12 19V5m0 0L6 11m6-6l6 6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

export default function FamilyTable({
  compact = false,
  initialFilter = "all",
  openFamilyId,
}: {
  /** For Home: fewer rows and a link to the full table. */
  compact?: boolean;
  initialFilter?: string;
  /** Opens this family's panel once the table has loaded. */
  openFamilyId?: number;
}) {
  const pageSize = compact ? 8 : 25;
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(initialFilter);
  const [sort, setSort] = useState<{ key: string; descending: boolean }>({ key: NAME, descending: false });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FamiliesTable | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [active, setActive] = useState<CellRef | null>(null);
  const [justSaved, setJustSaved] = useState<CellRef | null>(null);
  const [panel, setPanel] = useState<TableRow | null>(null);
  const [attempt, setAttempt] = useState(0);
  // A box he left before its save came back: the reason it was refused.
  const [lostEdit, setLostEdit] = useState<string | null>(null);

  // Opened from a link such as /families?family=12 (it may be on any page).
  useEffect(() => {
    if (!openFamilyId) return;
    getFamilyRow(openFamilyId).then(setPanel).catch(() => {});
  }, [openFamilyId]);

  // Wait until he stops typing before searching.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getFamiliesTable({ q: query, filter, sort: sort.key, descending: sort.descending, page, pageSize })
      .then((d) => live && setData(d))
      .catch((e) => live && setError(errorText(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [query, filter, sort, page, pageSize, attempt]);

  useEffect(() => {
    if (!justSaved) return;
    const timer = setTimeout(() => setJustSaved(null), 1500);
    return () => clearTimeout(timer);
  }, [justSaved]);

  const replaceRow = useCallback((row: TableRow) => {
    setData((d) => (d ? { ...d, rows: d.rows.map((r) => (r.family_id === row.family_id ? row : r)) } : d));
    setPanel((p) => (p && p.family_id === row.family_id ? row : p));
  }, []);

  const save = useCallback(
    async (familyId: number, key: string, value: string): Promise<string | null> => {
      try {
        const result = await editFamilyCell(familyId, key, value);
        replaceRow(result.row);
        if (result.changed) setJustSaved({ familyId, key });
        setLostEdit(null);
        return null;
      } catch (e) {
        return errorText(e);
      }
    },
    [replaceRow],
  );

  const setDocumentCount = useCallback((familyId: number, count: number) => {
    const update = (r: TableRow) =>
      r.family_id === familyId && r.values.documents !== count ? { ...r, values: { ...r.values, documents: count } } : r;
    setData((d) => (d ? { ...d, rows: d.rows.map(update) } : d));
    setPanel((p) => (p ? update(p) : p));
  }, []);

  const closePanel = useCallback(() => setPanel(null), []);

  function sortBy(column: TableColumn) {
    if (!column.sortable) return;
    setSort((s) => ({ key: column.key, descending: s.key === column.key ? !s.descending : false }));
    setPage(1);
  }

  /** Tab from a box: the next (or previous) editable box in the same row. */
  function move(from: CellRef, backwards: boolean) {
    const editableKeys = (data?.columns ?? []).filter((c) => c.editable).map((c) => c.key);
    const next = editableKeys[editableKeys.indexOf(from.key) + (backwards ? -1 : 1)];
    setActive(next ? { familyId: from.familyId, key: next } : null);
  }

  const columns = data?.columns ?? [];
  const lastPage = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const firstShown = data && data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const lastShown = data ? Math.min(data.page * data.page_size, data.total) : 0;

  return (
    <div className="min-w-0">
      {/* ---------- search, filters, editing ---------- */}
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative min-w-0 flex-1">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="2" />
            <path d="M16 16l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, soldier, army no., district, phone"
            aria-label="Search families"
            className="min-h-12 w-full rounded-full border border-border bg-bg pl-11 pr-4 text-[17px] outline-none focus:border-accent"
          />
        </div>
        <div className="flex items-center gap-2">
          <div className="no-scrollbar -mx-4 flex min-w-0 flex-1 gap-2 overflow-x-auto px-4 lg:mx-0 lg:px-0" role="group" aria-label="Show">
            {(data?.filters ?? [{ key: "all", label: "Everyone", count: 0 }]).map((f) => (
              <button
                key={f.key}
                aria-pressed={filter === f.key}
                onClick={() => {
                  setFilter(f.key);
                  setPage(1);
                }}
                className={`min-h-11 shrink-0 whitespace-nowrap rounded-full border px-4 text-[15px] transition ${
                  filter === f.key ? "border-accent bg-accent-soft font-semibold" : "border-border bg-bg text-muted hover:bg-surface-2 hover:text-text"
                }`}
              >
                {f.label}
                {data && <span className="ml-1.5 tabular-nums opacity-70">{f.count.toLocaleString("en-IN")}</span>}
              </button>
            ))}
          </div>
          <EditSwitch
            on={editing}
            onChange={(on) => {
              setEditing(on);
              setActive(null);
            }}
          />
        </div>
      </div>
      <p className="mb-3 text-[15px] text-muted">
        {editing
          ? "Tap a box to change it. Enter saves, Esc cancels. Old values are always kept in the history."
          : "Tap a name to see the whole family and its documents. Scroll sideways for more columns."}
      </p>

      {error && (
        <div className="mb-3 space-y-3">
          <Notice tone="danger" title="The families could not be loaded">
            {error}
          </Notice>
          <button onClick={() => setAttempt((n) => n + 1)} className={buttonSecondary}>
            Try again
          </button>
        </div>
      )}

      {lostEdit && (
        <div className="mb-3">
          <Notice tone="danger" title="One change was not saved" onClose={() => setLostEdit(null)}>
            {lostEdit}
          </Notice>
        </div>
      )}

      {/* ---------- the sheet ---------- */}
      {!data && !error ? (
        <div className="space-y-2" aria-hidden="true">
          {Array.from({ length: compact ? 5 : 8 }, (_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-surface" />
          ))}
        </div>
      ) : data ? (
        <div
          className={`relative max-h-[62dvh] overflow-auto rounded-2xl border border-border bg-surface transition-opacity sm:max-h-[70vh] ${
            loading ? "opacity-60" : ""
          }`}
          aria-busy={loading}
        >
          <table className="min-w-full border-separate border-spacing-0 text-left text-[15px]">
            <caption className="sr-only">Families, page {data.page} of {lastPage}</caption>
            <thead>
              <tr>
                {columns.map((c, index) => {
                  const direction = sort.key === c.key ? (sort.descending ? "desc" : "asc") : null;
                  return (
                    <th
                      key={c.key}
                      scope="col"
                      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : undefined}
                      className={`sticky top-0 whitespace-nowrap border-b border-border bg-surface-2 px-3 py-0 font-semibold ${
                        index === 0 ? "left-0 z-30 border-r" : "z-20"
                      } ${WIDTH[c.key] ?? "min-w-[8rem]"}`}
                    >
                      {c.sortable ? (
                        <button onClick={() => sortBy(c)} className="flex min-h-11 w-full items-center gap-1.5 text-left">
                          {c.label}
                          <SortArrow direction={direction} />
                        </button>
                      ) : (
                        <span className="flex min-h-11 items-center">{c.label}</span>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-10 text-[16px] text-muted">
                    {query ? `No family matches “${query}”.` : "No families here."}
                  </td>
                </tr>
              )}
              {data.rows.map((row) => (
                <tr key={row.family_id} className="group">
                  {columns.map((c, index) => {
                    const value = row.values[c.key];
                    const shown = display(c, value);
                    const isActive = active?.familyId === row.family_id && active.key === c.key;
                    const saved = justSaved?.familyId === row.family_id && justSaved.key === c.key;
                    const sticky = index === 0 ? "sticky left-0 z-10 border-r" : "";
                    const cell = `border-b border-border px-3 align-middle ${sticky} ${
                      saved ? "bg-accent-soft" : "bg-surface group-hover:bg-surface-2"
                    } ${WIDTH[c.key] ?? "min-w-[8rem]"}`;

                    if (c.key === NAME && !isActive) {
                      return (
                        <th key={c.key} scope="row" className={`${cell} py-0 font-medium`}>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setPanel(row)}
                              className="min-h-12 min-w-0 flex-1 truncate text-left underline-offset-4 hover:text-accent hover:underline"
                              title={shown}
                            >
                              {shown}
                            </button>
                            {editing && (
                              <button
                                onClick={() => setActive({ familyId: row.family_id, key: c.key })}
                                aria-label={`Change the name ${shown}`}
                                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-bg hover:text-accent"
                              >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                  <path d="M4 20h4L19 9l-4-4L4 16v4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
                                </svg>
                              </button>
                            )}
                          </div>
                        </th>
                      );
                    }

                    if (isActive) {
                      return (
                        <td key={c.key} className={`${cell} py-1.5`}>
                          <CellEditor
                            column={c}
                            initial={editable(c, value)}
                            onCancel={() => setActive(null)}
                            onTab={(backwards) => move({ familyId: row.family_id, key: c.key }, backwards)}
                            onSave={async (v) => {
                              const problem = await save(row.family_id, c.key, v);
                              setActive((a) => {
                                const stillHere = a?.familyId === row.family_id && a.key === c.key;
                                // He has moved on: the box is gone, so say it here instead.
                                if (problem && !stillHere) {
                                  setLostEdit(`${c.label} for ${row.values[NAME]} was not changed: ${problem}`);
                                }
                                return stillHere && !problem ? null : a;
                              });
                              return problem;
                            }}
                          />
                        </td>
                      );
                    }

                    const content =
                      c.key === "documents" ? (
                        <span className={`inline-flex items-center gap-1.5 ${Number(value) === 0 ? "font-medium text-warning" : ""}`}>
                          {Number(value) === 0 && (
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                              <path d="M12 3l10 18H2L12 3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
                              <path d="M12 10v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                            </svg>
                          )}
                          {Number(value) === 0 ? "None yet" : shown}
                        </span>
                      ) : shown ? (
                        <span className="block max-w-[18rem] truncate" title={shown}>
                          {shown}
                        </span>
                      ) : (
                        <span className="text-muted" aria-label="empty">—</span>
                      );

                    if (c.kind === "status") {
                      // "scheme.CEA" -> the CEA answer for this family.
                      const answer = row.eligibility[c.key.replace(/^scheme\./, "")];
                      return (
                        <td key={c.key} className={`${cell} py-0`}>
                          {answer ? (
                            <button
                              onClick={() => setPanel(row)}
                              title={answer.headline}
                              aria-label={`${c.label}: ${answer.label}. ${answer.headline}`}
                              className="flex min-h-12 w-full items-center text-left"
                            >
                              <EligibilityBadge status={answer.status} label={answer.label} small />
                            </button>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                      );
                    }

                    if (c.key === "documents") {
                      return (
                        <td key={c.key} className={`${cell} py-0`}>
                          <button onClick={() => setPanel(row)} className="flex min-h-12 w-full items-center text-left hover:underline">
                            {content}
                          </button>
                        </td>
                      );
                    }

                    if (editing && c.editable) {
                      return (
                        <td key={c.key} className={`${cell} py-0`}>
                          <button
                            onClick={() => setActive({ familyId: row.family_id, key: c.key })}
                            aria-label={`Change ${c.label} for ${row.values[NAME]}: ${shown || "empty"}`}
                            className="-mx-1.5 flex min-h-12 w-[calc(100%+0.75rem)] cursor-text items-center rounded-md px-1.5 text-left ring-inset hover:bg-bg hover:ring-1 hover:ring-accent/50"
                          >
                            {content}
                          </button>
                        </td>
                      );
                    }

                    return (
                      <td key={c.key} className={`${cell} h-12 whitespace-nowrap py-0 ${c.editable ? "" : "text-muted"}`}>
                        {content}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* ---------- pages ---------- */}
      {data && data.total > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p className="mr-auto text-[15px] text-muted" aria-live="polite">
            {firstShown}–{lastShown} of {data.total.toLocaleString("en-IN")}
          </p>
          {lastPage > 1 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page <= 1 || loading}
                className="min-h-11 rounded-full border border-border px-4 text-[16px] hover:bg-surface-2 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="px-1 text-[15px] tabular-nums text-muted">
                {data.page} / {lastPage}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
                disabled={data.page >= lastPage || loading}
                className="min-h-11 rounded-full border border-border px-4 text-[16px] hover:bg-surface-2 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
          {compact && (
            <Link href="/families" className="inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-full border border-border px-4 text-[16px] font-medium text-accent hover:bg-surface-2 sm:w-auto">
              Open the full table
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          )}
        </div>
      )}

      {panel && data && (
        <FamilyPanel
          row={panel}
          columns={data.columns}
          editing={editing}
          onSave={(key, value) => save(panel.family_id, key, value)}
          onDocuments={(count) => setDocumentCount(panel.family_id, count)}
          onClose={closePanel}
        />
      )}
    </div>
  );
}
