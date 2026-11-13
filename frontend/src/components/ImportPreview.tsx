"use client";

/**
 * The review: his sheet next to what is already saved, one family at a time.
 *
 * A family we already have (found by army number) shows only the values that
 * differ: the saved value, the sheet's value, a hint when it looks like a slip
 * ("Only 1 digit is different") and three choices: keep the saved value, use
 * the sheet's, or type the right one. New families, unchanged ones and skipped
 * rows sit in short lists below. Save stays off until every choice is made.
 */

import { useEffect, useState } from "react";
import ImportProgress from "@/components/ImportProgress";
import PreviewColumns from "@/components/PreviewColumns";
import RowEditor from "@/components/RowEditor";
import {
  commitImport,
  decideImportRow,
  editImportRow,
  previewImport,
  type CommitResult,
  type Comparison,
  type FieldChange,
  type PreviewResult,
  type RowPreview,
} from "@/lib/api";

type Props = {
  importId: number;
  /** True while rows are being checked or saved, so the page can hide "Choose another file". */
  onBusyChange?: (busy: boolean) => void;
  /** Called once the import has finished and the families are saved. */
  onFinished?: () => void;
  /** "Upload another sheet", shown after the import has finished. */
  onStartAgain?: () => void;
  /** How many rows he decided on, corrected or left out, so the page can warn before they are lost. */
  onEditsChange?: (rows: number) => void;
};

type Action = RowPreview["action"];
type Send = (body: Parameters<typeof decideImportRow>[2]) => Promise<void>;

/** Rows that ask something of him, in the order they are shown. */
const REVIEW: Action[] = ["possible_typo", "needs_decision", "lookalike_in_file", "update"];
const WRITES = (r: RowPreview) =>
  r.action === "create" ||
  r.action === "update" ||
  r.action === "possible_typo" ||
  r.action === "lookalike_in_file" ||
  (r.action === "needs_decision" && r.match_choice !== "leave");

const primary =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-accent px-6 text-[16px] font-semibold " +
  "text-accent-fg shadow-sm transition hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed " +
  "disabled:bg-surface-2 disabled:text-muted disabled:shadow-none";
const link = "text-[14px] font-medium text-accent underline-offset-4 hover:underline disabled:text-muted";

// ---------------------------------------------------------------- small parts

const Check = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const Hint = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="mt-0.5 shrink-0" aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
    <path d="M12 7.5v5.5M12 16.5v.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const Chevron = ({ open }: { open: boolean }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true">
    <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/**
 * Which letters of `value` differ from `other`: everything between the part
 * both share at the start and the part both share at the end. Only marked
 * when that is a small slip; two wholly different values are left plain.
 */
function Marked({ value, other }: { value: string | null; other: string | null }) {
  if (!value) return <span className="font-normal italic text-muted">blank</span>;
  if (!other || value === other) return <>{value}</>;
  let start = 0;
  while (start < value.length && start < other.length && value[start] === other[start]) start++;
  let end = 0;
  while (
    end < value.length - start &&
    end < other.length - start &&
    value[value.length - 1 - end] === other[other.length - 1 - end]
  )
    end++;
  const middle = value.slice(start, value.length - end);
  if (value.length - end - start > Math.max(3, value.length / 3)) return <>{value}</>;
  return (
    <>
      {value.slice(0, start)}
      {middle ? (
        <mark className="rounded bg-warning/20 px-0.5 font-bold text-warning ring-1 ring-warning/40">{middle}</mark>
      ) : (
        // A letter missing here: a thin mark where it would be.
        <mark className="mx-px inline-block h-[1.1em] w-0.5 translate-y-0.5 rounded bg-warning" aria-label="missing" />
      )}
      {value.slice(value.length - end)}
    </>
  );
}

/** "+919209665428" reads as "+91 92096 65428". Other values stay as they are. */
const spaced = (value: string | null) =>
  value?.replace(/^\+91(\d{5})(\d{5})$/, "+91 $1 $2") ?? null;

/** The sentence under a value, so he knows what to look at. */
function hintFor(change: FieldChange): { text: string; tone: "warn" | "info" } | null {
  if (change.typo) {
    const reason = change.typo.replace(/ different$/, " is different").replace(/^Only (\d+) digits is/, "Only $1 digits are");
    return { text: reason, tone: "warn" };
  }
  return null;
}

/** Three choices side by side, one picked. */
function Segmented<T extends string>({
  options,
  value,
  onPick,
  disabled,
  label,
}: {
  options: readonly (readonly [T, string])[];
  value: T | null;
  onPick: (choice: T) => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex gap-1 rounded-xl bg-surface-2 p-1">
      {options.map(([choice, text]) => {
        const on = value === choice;
        return (
          <button
            key={choice}
            type="button"
            onClick={() => onPick(choice)}
            disabled={disabled}
            aria-pressed={on}
            className={`inline-flex min-h-10 min-w-0 flex-1 basis-0 items-center justify-center gap-1 rounded-lg px-1.5 text-[14px] transition sm:gap-1.5 sm:px-3 ${
              on ? "bg-surface font-semibold text-accent shadow-sm ring-1 ring-border" : "text-muted hover:text-text"
            }`}
          >
            {on && <Check />}
            {text}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- one value

function ValueBox({ caption, children, picked }: { caption: string; children: React.ReactNode; picked: boolean }) {
  return (
    <div
      className={`min-w-0 rounded-xl border px-3 py-2.5 transition ${
        picked ? "border-accent bg-accent-soft" : "border-border bg-surface"
      }`}
    >
      <p className="flex items-center gap-1 text-[12px] font-semibold uppercase tracking-wide text-muted">
        {caption}
        {picked && (
          <span className="text-accent">
            <Check size={12} />
          </span>
        )}
      </p>
      <p className="mt-0.5 break-words text-[15px] font-medium sm:text-[16px]">{children}</p>
    </div>
  );
}

/** One value that differs: saved and sheet side by side, a hint, and his choice. */
function ChangeChoice({
  change,
  busy,
  send,
  type,
  several,
}: {
  change: FieldChange;
  /** More than one value differs on this family, so each says whether it is decided. */
  several: boolean;
  busy: boolean;
  send: Send;
  type: (fieldKey: string, value: string) => Promise<boolean>;
}) {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState(change.new_value ?? change.old_value ?? "");
  const hint = hintFor(change);
  const typed = change.decision === "typed";

  function pick(choice: "keep" | "excel" | "edit") {
    if (choice === "edit") {
      setDraft(change.new_value ?? change.old_value ?? "");
      setTyping(true);
      return;
    }
    setTyping(false);
    send({ decisions: { [change.field_name]: choice }, clear_typed: typed ? [change.field_key] : [] });
  }

  return (
    <li className="py-4 first:pt-1">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="text-[15px] font-semibold">{change.label}</p>
        {several && change.decision === null && <span className="text-[12px] font-semibold text-warning">To decide</span>}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <ValueBox caption="Saved" picked={change.decision === "keep"}>
          <Marked value={spaced(change.old_value)} other={spaced(change.new_value)} />
        </ValueBox>
        <ValueBox caption={typed ? "You typed" : "Sheet"} picked={change.decision === "excel" || typed}>
          {typed ? spaced(change.new_value) : <Marked value={spaced(change.new_value)} other={spaced(change.old_value)} />}
        </ValueBox>
      </div>

      {hint && (
        <p
          className={`mt-2 flex gap-1.5 text-[14px] leading-snug ${
            hint.tone === "warn" ? "font-medium text-warning" : "text-muted"
          }`}
        >
          <Hint />
          {hint.text}
        </p>
      )}

      <div className="mt-3">
        <Segmented
          label={`Which value for ${change.label}?`}
          options={[
            ["keep", "Keep saved"],
            ["excel", "Use sheet"],
            ["edit", "Edit"],
          ] as const}
          value={typing || typed ? "edit" : change.decision === "keep" || change.decision === "excel" ? change.decision : null}
          onPick={pick}
          disabled={busy}
        />
      </div>

      {typing && (
        <form
          className="mt-2 flex flex-wrap gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await type(change.field_key, draft.trim())) setTyping(false);
          }}
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label={`Correct value for ${change.label}`}
            autoFocus
            className="min-h-11 min-w-0 flex-1 basis-48 rounded-xl border border-accent bg-surface px-3 text-[16px] outline-none ring-4 ring-accent/10"
          />
          <button type="submit" disabled={busy || !draft.trim()} className={`${primary} min-h-11 px-5 text-[15px]`}>
            Save value
          </button>
          <button type="button" onClick={() => setTyping(false)} className="min-h-11 px-2 text-[15px] text-muted hover:text-text">
            Cancel
          </button>
        </form>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- side by side tables

const MARK: Record<Comparison["mark"], { label: string; tone: string }> = {
  "=": { label: "Same", tone: "text-success" },
  "~": { label: "Nearly", tone: "text-warning" },
  "!=": { label: "Different", tone: "text-danger" },
  "": { label: "", tone: "" },
};

function SideBySide({ rows, left, right }: { rows: Comparison[]; left: string; right: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[26rem] text-left text-[14px]">
        <thead className="bg-surface-2 text-[12px] uppercase tracking-wide text-muted">
          <tr>
            <th className="px-3 py-2 font-semibold" />
            <th className="px-3 py-2 font-semibold">{left}</th>
            <th className="px-3 py-2 font-semibold">{right}</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.label} className="border-t border-border">
              <td className="px-3 py-2 text-muted">{c.label}</td>
              <td className="px-3 py-2 font-medium">{c.database ?? "—"}</td>
              <td className="px-3 py-2 font-medium">{c.excel ?? "—"}</td>
              <td className={`px-3 py-2 text-right text-[12px] font-semibold ${MARK[c.mark].tone}`}>{MARK[c.mark].label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- one family

function FamilyCard({
  row,
  importId,
  onUpdated,
}: {
  row: RowPreview;
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const armyNumber = row.fields.find((f) => f.field_key === "service_number")?.value;
  const byArmyNumber = row.match_reasons.some((r) => /service number/i.test(r));
  const done = row.undecided === 0;

  async function run(work: () => Promise<PreviewResult>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      onUpdated(await work());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save that.");
      return false;
    } finally {
      setBusy(false);
    }
  }
  const send: Send = async (body) => {
    await run(() => decideImportRow(importId, row.row_number, body));
  };
  /** A value he typed, kept with the corrections he made before on this row. */
  const type = (fieldKey: string, value: string) => {
    const values: Record<string, string> = {};
    for (const f of row.fields) if (f.edited) values[f.field_key] = f.value;
    values[fieldKey] = value;
    return run(() => editImportRow(importId, row.row_number, { values, skip: row.skipped_by_user }));
  };
  const all = (choice: "keep" | "excel") =>
    send({
      decisions: Object.fromEntries(
        row.changes.filter((c) => c.decision !== "typed").map((c) => [c.field_name, choice]),
      ),
    });
  const showChanges = (row.action === "update" || row.action === "possible_typo" || row.match_choice === "same") && row.changes.length > 0;

  return (
    <li
      id={`row-${row.row_number}`}
      data-undecided={done ? undefined : ""}
      className={`scroll-mt-6 rounded-2xl border bg-surface shadow-sm transition ${done ? "border-border" : "border-warning/40"}`}
    >
      {/* ---------- who ---------- */}
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2 border-b border-border px-4 py-3.5 sm:px-5">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[17px] font-semibold">{row.widow_name || row.soldier_name || "(no name)"}</p>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-semibold ${
            done ? "bg-success/15 text-success" : "bg-warning/15 text-warning"
          }`}
        >
          {done ? (
            <>
              <Check size={12} /> Reviewed
            </>
          ) : (
            `${row.undecided} left`
          )}
        </span>
        {armyNumber && (
          <p className="flex basis-full items-center gap-1.5 text-[14px] text-muted">
            Army No. <span className="font-semibold text-text">{armyNumber}</span>
            {byArmyNumber && (
              <span className="text-success" title={`Matches saved family ${row.matched_family_code}`}>
                <Check size={13} />
              </span>
            )}
          </p>
        )}
      </div>

      <div className="px-4 py-3 sm:px-5">
        {/* ---------- might be a family we have ---------- */}
        {row.action === "needs_decision" && (
          <div className="space-y-3 py-1">
            <p className="text-[15px]">
              Same as <span className="font-semibold">{row.matched_family_code}</span>?
            </p>
            <SideBySide rows={row.comparison} left="Saved" right="Sheet" />
            <Segmented
              label="Is this the same family?"
              options={[
                ["same", "Same family"],
                ["new", "Different, add new"],
                ["leave", "Leave out"],
              ] as const}
              value={row.match_choice}
              onPick={(match) => send({ match })}
              disabled={busy}
            />
          </div>
        )}

        {/* ---------- two rows of this sheet alike ---------- */}
        {row.action === "lookalike_in_file" && (
          <div className="space-y-3 py-1">
            <p className="text-[15px]">
              Same as <span className="font-semibold">row {row.pair_with_row}</span>?
            </p>
            {/* pair_comparison: "excel" is the other row, "database" this one. */}
            <SideBySide
              rows={row.pair_comparison.map((c) => ({ ...c, database: c.excel, excel: c.database }))}
              left={`Row ${row.pair_with_row}`}
              right={`Row ${row.row_number}`}
            />
            <Segmented
              label="Which row to keep?"
              options={[
                ["first", `Keep row ${row.pair_with_row}`],
                ["second", `Keep row ${row.row_number}`],
                ["both", "Keep both"],
              ] as const}
              value={row.pair_choice}
              onPick={(pair) => send({ pair })}
              disabled={busy}
            />
          </div>
        )}
        {row.pair_choice && row.action !== "lookalike_in_file" && (
          <p className="py-1 text-[14px] text-muted">
            Looks like row {row.pair_with_row}: you chose{" "}
            {row.pair_choice === "both" ? "to keep both" : `to keep row ${row.pair_choice === "first" ? row.pair_with_row : row.row_number}`}.{" "}
            <button onClick={() => send({ pair: "undo" })} disabled={busy} className={link}>
              Change
            </button>
          </p>
        )}

        {/* ---------- the values that differ ---------- */}
        {showChanges && (
          <>
            {row.changes.length > 1 && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pb-1 pt-1 text-[14px]">
                <span className="text-muted">All:</span>
                <button onClick={() => all("keep")} disabled={busy} className={link}>
                  Keep saved
                </button>
                <button onClick={() => all("excel")} disabled={busy} className={link}>
                  Use sheet
                </button>
              </div>
            )}
            <ul className="divide-y divide-border">
              {row.changes.map((change) => (
                <ChangeChoice key={change.field_name} change={change} several={row.changes.length > 1} busy={busy} send={send} type={type} />
              ))}
            </ul>
          </>
        )}

        {row.problems.map((problem, i) => (
          <p key={i} className="flex gap-1.5 py-1 text-[14px] text-warning">
            <Hint />
            {problem.message}
          </p>
        ))}
        {error && <p className="py-1 text-[14px] text-danger">{error}</p>}

        <div className="flex justify-end">
          <button onClick={() => setEditing((v) => !v)} aria-expanded={editing} className={`${link} min-h-10`}>
            {editing ? "Close" : "Edit row"}
          </button>
        </div>
        {editing && (
          <RowEditor importId={importId} row={row} onUpdated={onUpdated} onClose={() => setEditing(false)} />
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- short lists

/** A quiet list that opens: new families, families with no change, rows skipped. */
function Fold({
  title,
  rows,
  importId,
  onUpdated,
  tone,
}: {
  title: string;
  rows: RowPreview[];
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
  tone: "add" | "skip";
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  if (rows.length === 0) return null;

  return (
    <section className="rounded-2xl border border-border bg-surface shadow-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-14 w-full items-center gap-3 rounded-2xl px-4 py-3 text-left hover:bg-surface-2/60 sm:px-5"
      >
        <span
          className={`flex h-9 min-w-9 items-center justify-center rounded-lg px-2 text-[15px] font-semibold tabular-nums ${
            tone === "add" ? "bg-success/15 text-success" : "bg-surface-2 text-muted"
          }`}
        >
          {rows.length}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[16px] font-semibold">{title}</span>
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <ul className="divide-y divide-border border-t border-border px-4 sm:px-5">
          {rows.map((row) => (
            <li key={row.row_number} className="py-2.5">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-[15px] font-medium ${row.skipped_by_user ? "text-muted line-through" : ""}`}>
                    {row.widow_name || row.soldier_name || "(no name)"}
                  </p>
                  <p className="truncate text-[13px] text-muted">
                    {[
                      `Row ${row.row_number}`,
                      row.district,
                      row.action === "unchanged" && row.matched_family_code && `already saved as ${row.matched_family_code}`,
                      row.duplicate_of_row && `exact copy of row ${row.duplicate_of_row}`,
                      row.action === "excluded" && row.note,
                      row.edited_fields.length > 0 && `${row.edited_fields.length} corrected`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {row.problems.map((problem, i) => (
                    <p key={i} className="text-[13px] text-warning">
                      {problem.message}
                    </p>
                  ))}
                </div>
                {row.fields.length > 0 && (
                  <button
                    onClick={() => setEditing(editing === row.row_number ? null : row.row_number)}
                    aria-expanded={editing === row.row_number}
                    className={`${link} min-h-10 shrink-0`}
                  >
                    {editing === row.row_number ? "Close" : "Edit"}
                  </button>
                )}
              </div>
              {editing === row.row_number && (
                <RowEditor importId={importId} row={row} onUpdated={onUpdated} onClose={() => setEditing(null)} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Shown instead of Save when no row would be written, with the reasons why. */
function NothingToImport({ counts }: { counts: PreviewResult["counts"] }) {
  const n = (action: Action) => counts[action] ?? 0;
  const s = (count: number) => (count === 1 ? "" : "s");
  const reasons = [
    n("unchanged") > 0 &&
      `${n("unchanged")} famil${n("unchanged") === 1 ? "y is" : "ies are"} already saved with the same details.`,
    n("duplicate_in_file") > 0 &&
      `${n("duplicate_in_file")} row${s(n("duplicate_in_file"))} ${n("duplicate_in_file") === 1 ? "is an exact copy" : "are exact copies"} of another row.`,
    n("excluded") > 0 && `${n("excluded")} row${s(n("excluded"))} you left out.`,
    n("skipped") > 0 && `${n("skipped")} row${s(n("skipped"))} could not be used.`,
  ].filter(Boolean) as string[];

  return (
    <div className="rounded-2xl border border-border bg-surface px-5 py-4 shadow-sm" role="status">
      <p className="text-[17px] font-semibold">Nothing new to save</p>
      {reasons.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px]">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[15px] text-muted">To add or update families, change the sheet and upload it again.</p>
    </div>
  );
}


// ---------------------------------------------------------------- the page

export default function ImportPreview({ importId, onBusyChange, onFinished, onStartAgain, onEditsChange }: Props) {
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const busy = importing || (!preview && !error);
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);
  useEffect(() => {
    if (result) onFinished?.();
  }, [result, onFinished]);
  useEffect(() => {
    if (!preview) return;
    onEditsChange?.(
      preview.rows.filter(
        (r) =>
          r.edited_fields.length > 0 ||
          r.skipped_by_user ||
          r.match_choice !== null ||
          r.pair_choice !== null ||
          r.changes.some((c) => c.decision !== null),
      ).length,
    );
  }, [preview, onEditsChange]);
  useEffect(() => {
    let cancelled = false;
    previewImport(importId)
      .then((data) => !cancelled && setPreview(data))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not build the review."));
    return () => {
      cancelled = true;
    };
  }, [importId]);

  async function runImport() {
    setImporting(true);
    setError(null);
    try {
      setResult(await commitImport(importId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The save failed.");
    } finally {
      setImporting(false);
    }
  }

  if (error && !preview) return <p className="text-[17px] text-danger">{error}</p>;
  // The save checks the rows once more, then writes: the card follows both.
  if (!preview || importing) return <ImportProgress step="checking" importId={importId} />;

  if (result) {
    const lines = [
      [result.created, "families added"],
      [result.updated, "families updated"],
      [result.fields_changed, "values changed, old ones kept"],
      [result.unchanged, "already correct"],
    ] as const;
    return (
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-success/15 text-success">
            <Check size={22} />
          </span>
          <h2 className="text-[20px] font-semibold">Everything is saved</h2>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {lines.map(([value, label]) => (
            <div key={label} className="rounded-xl bg-surface-2 px-4 py-3">
              <dt className="text-[14px] text-muted">{label}</dt>
              <dd className="text-[24px] font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        <ul className="mt-4 space-y-1 text-[15px] text-muted">
          {result.fields_corrected > 0 && <li>{result.fields_corrected} values you typed are recorded as changed by you.</li>}
          {result.duplicates_flagged > 0 && <li>{result.duplicates_flagged} repeated rows were not saved.</li>}
          {result.excluded > 0 && <li>{result.excluded} rows you left out were not saved.</li>}
          {result.skipped > 0 && <li>{result.skipped} rows could not be used.</li>}
          {result.issues_raised > 0 && (
            <li className="font-medium text-warning">{result.issues_raised} items added to the needs-attention list.</li>
          )}
        </ul>
        {onStartAgain && (
          <button onClick={onStartAgain} className={`${primary} mt-5 w-full sm:w-auto`}>
            Upload another sheet
          </button>
        )}
      </div>
    );
  }

  const rowsOf = (...actions: Action[]) => preview.rows.filter((r) => actions.includes(r.action));
  const review = REVIEW.flatMap((action) => rowsOf(action));
  const added = rowsOf("create");
  const same = rowsOf("unchanged");
  const skipped = rowsOf("duplicate_in_file", "excluded", "skipped");
  const willWrite = preview.rows.filter(WRITES).length;
  const left = Object.values(preview.undecided ?? {}).reduce((a, n) => a + n, 0);

  function nextToReview() {
    document.querySelector("[data-undecided]")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="space-y-6 pb-4">
      {/* ---------- at a glance ---------- */}
      <p className="text-[15px] text-muted">
        {[
          review.length && `${review.length} to review`,
          added.length && `${added.length} new`,
          same.length && `${same.length} no change`,
          skipped.length && `${skipped.length} skipped`,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>

      <PreviewColumns preview={preview} onUpdated={setPreview} />

      {/* ---------- families we have, side by side ---------- */}
      {review.length > 0 && (
        <section>
          <h2 className="text-[20px] font-semibold tracking-tight">To review</h2>
          <ul className="mt-3 space-y-4">
            {review.map((row) => (
              <FamilyCard key={row.row_number} row={row} importId={importId} onUpdated={setPreview} />
            ))}
          </ul>
        </section>
      )}

      {/* ---------- everything else ---------- */}
      <div className="space-y-3">
        <Fold title="New families" rows={added} importId={importId} onUpdated={setPreview} tone="add" />
        <Fold title="No change" rows={same} importId={importId} onUpdated={setPreview} tone="skip" />
        <Fold title="Skipped" rows={skipped} importId={importId} onUpdated={setPreview} tone="skip" />
      </div>

      {/* ---------- save ---------- */}
      {willWrite === 0 ? (
        <NothingToImport counts={preview.counts} />
      ) : (
        <div className="sticky bottom-3 z-10 flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-surface/95 px-4 py-3 shadow-lg backdrop-blur sm:px-5">
          <div className="min-w-0 flex-1">
            {left > 0 ? (
              <>
                <button onClick={nextToReview} className="text-[16px] font-semibold hover:underline">
                  {left} left to review
                </button>
              </>
            ) : (
              <>
                <p className="flex items-center gap-1.5 text-[16px] font-semibold text-success">
                  <Check /> All reviewed
                </p>
              </>
            )}
            {error && <p className="text-[14px] text-danger">{error}</p>}
          </div>
          <button onClick={runImport} disabled={left > 0} className={`${primary} w-full sm:w-auto`}>
            Save {willWrite} famil{willWrite === 1 ? "y" : "ies"}
          </button>
        </div>
      )}
    </div>
  );
}
