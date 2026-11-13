"use client";

/**
 * Every family as one table, like his Excel sheet: read it, search it, sort it.
 *
 * The table itself cannot be changed by a stray click. The ✏️ next to a name
 * is the only way in: it opens the whole family, where each detail changes
 * only when he presses Save. On a phone the table scrolls sideways with the
 * name pinned on the left. Every change goes through the server's checks,
 * and the old value is kept in history.
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

/** Does this box contain what he searched for? Phones are checked with and without spaces. */
function matchesSearch(column: TableColumn, value: Value, query: string): boolean {
  if (!query || value === null || value === "" || column.kind === "status" || column.kind === "profile" || column.key === "documents") return false;
  const needle = query.toLowerCase();
  return display(column, value).toLowerCase().includes(needle) || String(value).toLowerCase().includes(needle);
}

/** The searched word marked in yellow; stronger on the family the arrows are on. */
function Highlight({ text, raw, query, current }: { text: string; raw: string; query: string; current: boolean }) {
  if (!query) return <>{text}</>;
  const mark = `rounded-sm px-0.5 ${current ? "bg-warning text-bg" : "bg-warning/25 text-inherit"}`;
  const lower = text.toLowerCase();
  const needle = query.toLowerCase();
  // "9876543210" is shown as "+91 98765 43210": mark the whole number.
  if (!lower.includes(needle)) {
    return raw.toLowerCase().includes(needle) ? <mark className={mark}>{text}</mark> : <>{text}</>;
  }
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (let i = lower.indexOf(needle); i !== -1; i = lower.indexOf(needle, at)) {
    if (i > at) parts.push(text.slice(at, i));
    parts.push(
      <mark key={i} className={mark}>
        {text.slice(i, i + needle.length)}
      </mark>,
    );
    at = i + needle.length;
  }
  parts.push(text.slice(at));
  return <>{parts}</>;
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
  profile: "min-w-[6.5rem]",
  documents: "min-w-[7rem]",
  children: "min-w-[6rem]",
  unit: "min-w-[11rem]",
  email: "min-w-[15rem]",
  bank_name: "min-w-[11rem]",
  bank_address: "min-w-[14rem]",
  correspondence_address: "min-w-[14rem]",
  record_office: "min-w-[14rem]",
  notes: "min-w-[14rem]",
};

// --- how complete the profile is --------------------------------------------

/** A ring that fills up like a clock, with the percentage inside. */
function ProfileRing({ percent, size = 40 }: { percent: number; size?: number }) {
  const stroke = size >= 56 ? 6 : 4;
  const radius = (size - stroke) / 2;
  const around = 2 * Math.PI * radius;
  const tone = percent === 100 ? "text-success" : percent >= 50 ? "text-warning" : "text-danger";
  return (
    <span className={`relative inline-flex shrink-0 items-center justify-center ${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="currentColor" strokeOpacity={0.18} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={around}
          strokeDashoffset={around * (1 - percent / 100)}
        />
      </svg>
      <span
        className="absolute font-semibold tabular-nums text-text"
        style={{ fontSize: size >= 56 ? 16 : 11 }}
        aria-label={`Profile ${percent}% complete`}
      >
        {percent}%
      </span>
    </span>
  );
}

// --- the editor used in the family panel -----------------------------------

function CellEditor({
  column,
  initial,
  onSave,
  onCancel,
}: {
  column: TableColumn;
  initial: string;
  /** Resolves to an error message, or null when saved. */
  onSave: (value: string) => Promise<string | null>;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement & HTMLSelectElement>(null);

  useEffect(() => {
    ref.current?.focus();
    if (ref.current && "select" in ref.current && column.kind !== "choice") ref.current.select();
  }, [column.kind]);

  // Only the Save button saves: Enter, Tab or clicking away never do.
  async function commit() {
    if (saving) return;
    if (draft.trim() === initial.trim()) {
      onCancel();
      return;
    }
    setSaving(true);
    const problem = await onSave(draft);
    setSaving(false);
    setError(problem);
  }

  const base = `min-h-12 w-full rounded-lg border bg-bg px-3 text-[17px] outline-none focus:border-accent ${
    error ? "border-danger" : "border-accent"
  }`;

  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
    } else if (e.key === "Escape") {
      e.preventDefault();
      // Esc here closes this box only, not the whole family.
      e.stopPropagation();
      onCancel();
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
          aria-label={column.label}
          aria-invalid={error ? true : undefined}
          inputMode={column.kind === "phone" ? "tel" : column.kind === "date" || column.kind === "number" ? "numeric" : undefined}
          placeholder={column.kind === "date" ? "DD-MM-YYYY" : column.required ? "Needed" : ""}
          autoComplete="off"
          className={base}
        />
      )}
      {error && <p className="mt-1 whitespace-normal text-[14px] leading-snug text-danger">{error}</p>}
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
    </div>
  );
}

// --- the family, as a list (opens from the ✏️ next to a name) --------------

function FamilyPanel({
  row,
  columns,
  onSave,
  onDocuments,
  onClose,
}: {
  row: TableRow;
  columns: TableColumn[];
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

  // Every detail, under the same headings as his sheet (Soldier, Address, Children...).
  const groups: { title: string; columns: TableColumn[] }[] = [];
  for (const c of columns) {
    if (c.key === "documents" || c.kind === "status" || c.kind === "profile") continue;
    const last = groups[groups.length - 1];
    if (last?.title === c.group) last.columns.push(c);
    else groups.push({ title: c.group, columns: [c] });
  }

  // A child who isn't recorded yet shows only their name box ("+ Add Child 2"),
  // and only once the child before them exists.
  const childSlot = (title: string) => Number(/^Child (\d)$/.exec(title)?.[1] ?? 0);
  const hasChild = (slot: number) => Boolean(row.values[`child${slot}_name`]);

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
          <div className="mb-3 mt-2 flex items-start gap-4 rounded-2xl border border-border bg-surface p-4">
            <ProfileRing percent={Number(row.values.profile ?? 0)} size={64} />
            <div className="min-w-0 flex-1">
              <p className="text-[17px] font-semibold">Profile {Number(row.values.profile ?? 0)}% complete</p>
              {row.missing.length === 0 ? (
                <p className="text-[15px] text-muted">Every detail is filled in.</p>
              ) : (
                <details className="text-[15px] text-muted">
                  <summary className="cursor-pointer py-1 text-accent">
                    {row.missing.length} {row.missing.length === 1 ? "detail" : "details"} still missing
                  </summary>
                  <p className="mt-1 leading-relaxed">{row.missing.join(", ")}</p>
                </details>
              )}
            </div>
          </div>
          <p className="mb-2 text-[14px] text-muted">Press Change, type, then Save. Nothing is saved until you press Save.</p>
          {groups.map((group) => {
            const slot = childSlot(group.title);
            if (slot > 1 && !hasChild(slot - 1)) return null;
            const nameKey = `child${slot}_name`;
            if (slot && !hasChild(slot) && open !== nameKey) {
              return (
                <section key={group.title} className="mt-5">
                  <h4 className="border-b-2 border-border pb-1.5 text-[15px] font-semibold uppercase tracking-wide text-muted">
                    {group.title}
                  </h4>
                  <div className="flex items-center gap-2 py-3">
                    <span className="flex-1 text-[17px] text-muted">No child yet.</span>
                    <button
                      onClick={() => setOpen(nameKey)}
                      className="min-h-11 shrink-0 rounded-full border border-border px-4 text-[15px] font-medium text-accent hover:bg-surface-2"
                    >
                      + Add Child {slot}
                    </button>
                  </div>
                </section>
              );
            }
            const shownColumns = slot && !hasChild(slot) ? group.columns.filter((c) => c.key === nameKey) : group.columns;
            return (
            <section key={group.title} className="mt-5">
              <h4 className="border-b-2 border-border pb-1.5 text-[15px] font-semibold uppercase tracking-wide text-muted">
                {group.title}
              </h4>
              <dl className="divide-y divide-border">
                {shownColumns.map((c) => (
                  <div key={c.key} className="py-3">
                    <dt className="text-[14px] text-muted">{c.label}</dt>
                    {open === c.key ? (
                      <dd className="mt-1">
                        <CellEditor
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
                        {c.editable && (
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
            </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// --- the table --------------------------------------------------------------

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
  const [justSaved, setJustSaved] = useState<CellRef | null>(null);
  const [panel, setPanel] = useState<TableRow | null>(null);
  const [attempt, setAttempt] = useState(0);
  // The ↑ ↓ arrows: which row of this page they are on, and where to land after a page turn.
  const [current, setCurrent] = useState(0);
  const landAt = useRef<"first" | "last">("first");
  const jumped = useRef(false);
  const scroller = useRef<HTMLDivElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);

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
      .then((d) => {
        if (!live) return;
        setData(d);
        setCurrent(landAt.current === "last" ? Math.max(0, d.rows.length - 1) : 0);
        landAt.current = "first";
      })
      .catch((e) => live && setError(errorText(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [query, filter, sort, page, pageSize, attempt]);

  // After an arrow press, bring the marked box into view (sideways too).
  useEffect(() => {
    if (!jumped.current) return;
    jumped.current = false;
    scroller.current
      ?.querySelector("[data-current-match]")
      ?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [current, data]);

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

  const columns = data?.columns ?? [];
  const lastPage = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const firstShown = data && data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const lastShown = data ? Math.min(data.page * data.page_size, data.total) : 0;
  const showArrows = Boolean(query && data && data.total > 0);
  const position = firstShown + current;

  /** ↑ (-1) or ↓ (+1): the next family that matches, turning the page if needed. */
  function step(direction: 1 | -1) {
    if (!data || loading || !data.rows.length) return;
    const next = current + direction;
    jumped.current = true;
    if (next >= 0 && next < data.rows.length) {
      setCurrent(next);
    } else if (direction === 1 && data.page < lastPage) {
      landAt.current = "first";
      setPage(data.page + 1);
    } else if (direction === -1 && data.page > 1) {
      landAt.current = "last";
      setPage(data.page - 1);
    } else {
      jumped.current = false;
    }
  }

  function searchKeys(e: React.KeyboardEvent) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    // Enter before the search has caught up: search now instead of moving.
    if (search.trim() !== query) {
      setQuery(search.trim());
      setPage(1);
    } else {
      step(e.shiftKey ? -1 : 1);
    }
  }

  return (
    <div className="min-w-0">
      {/* ---------- search and filters ---------- */}
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative min-w-0 flex-1">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="2" />
            <path d="M16 16l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            ref={searchBox}
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={searchKeys}
            placeholder="Search name, soldier, army no., district, phone"
            aria-label="Search families"
            // The browser's own ✕ only shows on hover; ours below is always there.
            className={`min-h-12 w-full rounded-full border border-border bg-bg pl-11 text-[17px] outline-none focus:border-accent [&::-webkit-search-cancel-button]:hidden ${
              showArrows ? "pr-[13rem]" : search ? "pr-12" : "pr-4"
            }`}
          />
          {search && (
            <div className="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setQuery("");
                  setPage(1);
                  searchBox.current?.focus();
                }}
                aria-label="Clear the search"
                title="Clear the search"
                className="flex h-10 w-10 items-center justify-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
                </svg>
              </button>
              {showArrows && data && (
              <>
              <span className="whitespace-nowrap px-1.5 text-[14px] tabular-nums text-muted" aria-live="polite">
                {position.toLocaleString("en-IN")} of {data.total.toLocaleString("en-IN")}
              </span>
              {([-1, 1] as const).map((direction) => (
                <button
                  key={direction}
                  type="button"
                  onClick={() => step(direction)}
                  disabled={loading || (direction === -1 ? position <= 1 : position >= data.total)}
                  aria-label={direction === -1 ? "Previous match" : "Next match"}
                  title={direction === -1 ? "Previous match (Shift+Enter)" : "Next match (Enter)"}
                  className="flex h-10 w-10 items-center justify-center rounded-full text-text hover:bg-surface-2 disabled:opacity-30"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d={direction === -1 ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"}
                      stroke="currentColor"
                      strokeWidth="2.25"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              ))}
              </>
              )}
            </div>
          )}
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
        </div>
      </div>
      <p className="mb-3 text-[15px] text-muted">
        Press ✏️ next to a name to see or change that family. Scroll sideways for more columns.
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

      {/* ---------- the sheet ---------- */}
      {!data && !error ? (
        <div className="space-y-2" aria-hidden="true">
          {Array.from({ length: compact ? 5 : 8 }, (_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-surface" />
          ))}
        </div>
      ) : data ? (
        <div
          ref={scroller}
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
              {data.rows.map((row, rowIndex) => {
                const matched = query ? columns.filter((c) => matchesSearch(c, row.values[c.key], query)).map((c) => c.key) : [];
                const isCurrentRow = showArrows && rowIndex === current;
                return (
                <tr key={row.family_id} className="group">
                  {columns.map((c, index) => {
                    const value = row.values[c.key];
                    const shown = display(c, value);
                    const saved = justSaved?.familyId === row.family_id && justSaved.key === c.key;
                    const sticky = index === 0 ? "sticky left-0 z-10 border-r" : "";
                    // Scroll margins keep the box clear of the pinned name column and header.
                    const cell = `border-b border-border px-3 align-middle scroll-mt-12 scroll-ml-[12rem] sm:scroll-ml-[17rem] ${sticky} ${
                      saved ? "bg-accent-soft" : "bg-surface group-hover:bg-surface-2"
                    } ${WIDTH[c.key] ?? "min-w-[8rem]"}`;
                    const found = (
                      <Highlight
                        text={shown}
                        raw={String(value ?? "")}
                        query={matched.includes(c.key) ? query : ""}
                        current={isCurrentRow}
                      />
                    );
                    const target = isCurrentRow && matched[0] === c.key ? { "data-current-match": true } : {};

                    if (c.key === NAME) {
                      return (
                        <th key={c.key} scope="row" className={`${cell} py-0 font-medium`} {...target}>
                          <div className="flex items-center gap-1">
                            <span className="flex min-h-12 min-w-0 flex-1 items-center truncate" title={shown}>
                              <span className="truncate">{found}</span>
                            </span>
                            {/* The only way into a family: nothing else in the table can be clicked. */}
                            <button
                              onClick={() => setPanel(row)}
                              aria-label={`See or change ${shown}`}
                              title="See or change this family"
                              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-bg hover:text-accent"
                            >
                              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                <path d="M4 20h4L19 9l-4-4L4 16v4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
                              </svg>
                            </button>
                          </div>
                        </th>
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
                          {found}
                        </span>
                      ) : (
                        <span className="text-muted" aria-label="empty">—</span>
                      );

                    if (c.kind === "profile") {
                      // What is missing is listed in the family panel (✏️), not in a pop-up here.
                      return (
                        <td key={c.key} className={`${cell} py-1`}>
                          <ProfileRing percent={Number(value ?? 0)} />
                        </td>
                      );
                    }

                    if (c.kind === "status") {
                      // "scheme.CEA" -> the CEA answer for this family.
                      const answer = row.eligibility[c.key.replace(/^scheme\./, "")];
                      return (
                        <td key={c.key} className={`${cell} py-0`}>
                          {answer ? (
                            <span title={answer.headline} className="flex min-h-12 items-center">
                              <EligibilityBadge status={answer.status} label={answer.label} small />
                            </span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                      );
                    }

                    return (
                      <td key={c.key} className={`${cell} h-12 whitespace-nowrap py-0 ${c.editable ? "" : "text-muted"}`} {...target}>
                        {content}
                      </td>
                    );
                  })}
                </tr>
                );
              })}
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
          onSave={(key, value) => save(panel.family_id, key, value)}
          onDocuments={(count) => setDocumentCount(panel.family_id, count)}
          onClose={closePanel}
        />
      )}
    </div>
  );
}
