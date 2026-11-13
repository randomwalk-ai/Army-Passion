"use client";

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
  type FieldChange,
  type PreviewResult,
  type RowPreview,
} from "@/lib/api";

type Props = {
  importId: number;
  /** True while rows are being checked or saved, so the page can hide "Back". */
  onBusyChange?: (busy: boolean) => void;
  /** Called once the import has finished and the families are saved. */
  onFinished?: () => void;
  /** "Upload another sheet", shown after the import has finished. */
  onStartAgain?: () => void;
  /** How many rows he corrected or left out, so the page can warn before they are lost. */
  onEditsChange?: (rows: number) => void;
};

const ACTION_LABELS: Record<RowPreview["action"], string> = {
  possible_typo: "Possible typos",
  needs_decision: "Possible duplicates",
  lookalike_in_file: "Possibly the same family twice in this sheet",
  update: "Updates to families you already have",
  create: "New families",
  unchanged: "Already in the database, no changes",
  duplicate_in_file: "Exact copies in this sheet",
  skipped: "No name. Use Edit to add one",
  excluded: "You left these out",
};

// The groups, under what he has to do: decide, nothing (added), nothing (skipped).
// Each heading's colour, on the count pills and the cards' left edge:
// amber to decide, green to add, grey to skip.
// Written out in full so Tailwind keeps the classes.
const TONES = {
  decide: { pill: "bg-warning/15 text-warning", edge: "border-l-warning/70" },
  add: { pill: "bg-success/15 text-success", edge: "border-l-success/70" },
  skip: { pill: "bg-surface-2 text-muted", edge: "border-l-border" },
};

const Chevron = ({ open }: { open: boolean }) => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    className={`shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`}
    aria-hidden="true"
  >
    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

type Tone = (typeof TONES)[keyof typeof TONES];

const SECTIONS: { title: string; tone: Tone; actions: RowPreview["action"][] }[] = [
  {
    title: "Needs your decision",
    tone: TONES.decide,
    actions: ["lookalike_in_file", "possible_typo", "needs_decision", "update"],
  },
  {
    title: "Will be added",
    tone: TONES.add,
    actions: ["create"],
  },
  {
    title: "Will be skipped",
    tone: TONES.skip,
    actions: ["duplicate_in_file", "unchanged", "excluded", "skipped"],
  },
];

type Send = (body: Parameters<typeof decideImportRow>[2]) => Promise<void>;

const choiceButton = (on: boolean) =>
  `min-h-10 rounded-full border px-3.5 text-[14px] transition ${
    on ? "border-accent bg-accent font-semibold text-accent-fg" : "border-border bg-bg text-text hover:bg-surface-2"
  }`;

/** One value that would change: the sheet and the database side by side, and his choice. */
function ChangeChoice({
  change,
  busy,
  send,
  type,
}: {
  change: FieldChange;
  busy: boolean;
  send: Send;
  type: (fieldKey: string, value: string) => Promise<boolean>;
}) {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState(change.new_value ?? "");
  const choose = (choice: "keep" | "excel") =>
    send({
      decisions: { [change.field_name]: choice },
      clear_typed: change.decision === "typed" ? [change.field_key] : [],
    });

  return (
    <li className="rounded-lg border border-border bg-bg px-3 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-[14px] font-medium">{change.label}</span>
        {change.typo ? (
          <span className="text-[13px] font-medium text-warning">{change.typo}</span>
        ) : (
          <span className="text-[13px] text-muted">Changed</span>
        )}
      </div>
      <div className="mt-1 grid gap-x-4 gap-y-0.5 text-[15px] sm:grid-cols-2">
        <span className="min-w-0 [overflow-wrap:anywhere]">
          <span className="text-[13px] text-muted">Excel: </span>
          {change.decision === "typed" ? (
            <span className="font-medium text-accent">{change.new_value} (you typed)</span>
          ) : (
            <span className="font-medium">{change.new_value ?? "(blank)"}</span>
          )}
        </span>
        <span className="min-w-0 [overflow-wrap:anywhere]">
          <span className="text-[13px] text-muted">Database: </span>
          <span className="font-medium">{change.old_value ?? "(blank)"}</span>
        </span>
      </div>

      {typing ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label={`Correct value for ${change.label}`}
            autoFocus
            className="min-h-10 min-w-0 flex-1 basis-48 rounded-lg border border-accent bg-bg px-3 text-[15px] outline-none"
          />
          <button
            onClick={async () => (await type(change.field_key, draft)) && setTyping(false)}
            disabled={busy || !draft.trim()}
            className="min-h-10 rounded-full bg-accent px-4 text-[14px] font-semibold text-accent-fg disabled:bg-surface-2 disabled:text-muted"
          >
            Save
          </button>
          <button onClick={() => setTyping(false)} className="min-h-10 px-2 text-[14px] text-muted underline">
            Cancel
          </button>
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label={`Which value for ${change.label}?`}>
          <button onClick={() => choose("keep")} disabled={busy} aria-pressed={change.decision === "keep"} className={choiceButton(change.decision === "keep")}>
            Keep database
          </button>
          <button onClick={() => choose("excel")} disabled={busy} aria-pressed={change.decision === "excel"} className={choiceButton(change.decision === "excel")}>
            Take Excel
          </button>
          <button onClick={() => setTyping(true)} disabled={busy} aria-pressed={change.decision === "typed"} className={choiceButton(change.decision === "typed")}>
            Type correct value
          </button>
        </div>
      )}
    </li>
  );
}

const MARK: Record<string, { sign: string; tone: string }> = {
  "=": { sign: "=", tone: "text-muted" },
  "~": { sign: "≈", tone: "text-text" },
  "!=": { sign: "≠", tone: "text-text" },
  "": { sign: "", tone: "" },
};

/** A possible duplicate: the sheet row next to the family it might be. */
function DuplicateChoice({ row, busy, send }: { row: RowPreview; busy: boolean; send: Send }) {
  return (
    <div className="rounded-lg border border-border bg-bg px-3 py-3">
      <p className="text-[15px]">
        Might be <span className="font-semibold">{row.matched_family_code}</span>{" "}
        <span className="text-muted">({row.match_score}% alike)</span>
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[22rem] text-left text-[14px]">
          <thead>
            <tr className="text-[13px] text-muted">
              <th className="py-1 pr-2 font-normal" />
              <th className="py-1 pr-2 font-normal">Excel</th>
              <th className="w-6 py-1" />
              <th className="py-1 font-normal">Database</th>
            </tr>
          </thead>
          <tbody>
            {row.comparison.map((c) => (
              <tr key={c.label} className="border-t border-border">
                <td className="py-1.5 pr-2 text-muted">{c.label}</td>
                <td className="py-1.5 pr-2 font-medium">{c.excel ?? "—"}</td>
                <td className={`py-1.5 text-center text-[16px] font-semibold ${MARK[c.mark].tone}`} aria-label={c.mark}>
                  {MARK[c.mark].sign}
                </td>
                <td className="py-1.5 font-medium">{c.database ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Is this the same family?">
        {(
          [
            ["same", "Same family, update it"],
            ["new", "Different family, add new"],
            ["leave", "Leave out"],
          ] as const
        ).map(([choice, label]) => (
          <button
            key={choice}
            onClick={() => send({ match: choice })}
            disabled={busy}
            aria-pressed={row.match_choice === choice}
            className={choiceButton(row.match_choice === choice)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Two rows of this sheet that look like one family: which to keep. */
function PairChoice({ row, busy, send }: { row: RowPreview; busy: boolean; send: Send }) {
  const other = row.pair_with_row;
  return (
    <div className="rounded-lg border border-border bg-bg px-3 py-3">
      <p className="text-[15px]">
        Looks like <span className="font-semibold">row {other}</span>{" "}
        <span className="text-muted">({row.pair_score}% alike)</span>
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[22rem] text-left text-[14px]">
          <thead>
            <tr className="text-[13px] text-muted">
              <th className="py-1 pr-2 font-normal" />
              <th className="py-1 pr-2 font-normal">Row {other}</th>
              <th className="w-6 py-1" />
              <th className="py-1 font-normal">Row {row.row_number}</th>
            </tr>
          </thead>
          <tbody>
            {row.pair_comparison.map((c) => (
              <tr key={c.label} className="border-t border-border">
                <td className="py-1.5 pr-2 text-muted">{c.label}</td>
                <td className="py-1.5 pr-2 font-medium">{c.excel ?? "—"}</td>
                <td className={`py-1.5 text-center text-[16px] font-semibold ${MARK[c.mark].tone}`} aria-label={c.mark}>
                  {MARK[c.mark].sign}
                </td>
                <td className="py-1.5 font-medium">{c.database ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Which row to keep?">
        {(
          [
            ["first", `Keep row ${other}`],
            ["second", `Keep row ${row.row_number}`],
            ["both", "Different families, keep both"],
          ] as const
        ).map(([choice, label]) => (
          <button
            key={choice}
            onClick={() => send({ pair: choice })}
            disabled={busy}
            aria-pressed={row.pair_choice === choice}
            className={choiceButton(row.pair_choice === choice)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Row({
  row,
  importId,
  onUpdated,
}: {
  row: RowPreview;
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
}) {
  // A row waiting for his choice opens by itself: the choice is the point.
  const [open, setOpen] = useState(
    row.undecided > 0 || row.action === "needs_decision" || row.action === "lookalike_in_file",
  );
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = row.widow_name || row.soldier_name || "(no name)";
  const hasDetail =
    row.changes.length > 0 ||
    row.problems.length > 0 ||
    row.match_reasons.length > 0 ||
    row.comparison.length > 0 ||
    row.pair_comparison.length > 0;
  const decidable = row.action !== "create" && row.action !== "unchanged";

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

  return (
    <li
      id={`row-${row.row_number}`}
      data-undecided={row.undecided > 0 ? "" : undefined}
      className="scroll-mt-24 border-t border-border py-2.5"
    >
      <div className="flex items-start gap-2 sm:gap-3">
        <button
          onClick={() => hasDetail && setOpen((v) => !v)}
          aria-expanded={hasDetail ? open : undefined}
          className={`flex min-w-0 flex-1 flex-wrap items-start gap-x-3 gap-y-1 text-left ${
            hasDetail ? "" : "cursor-default"
          }`}
        >
          <span className="w-12 shrink-0 pt-0.5 text-xs text-muted">
            Row {row.row_number}
          </span>
          <span className="min-w-0 flex-1 basis-40">
            <span
              className={`block truncate text-[15px] font-medium ${
                row.skipped_by_user ? "text-muted line-through" : ""
              }`}
            >
              {who}
            </span>
            <span className="block truncate text-xs text-muted">
              {row.district}
              {row.matched_family_code &&
                (row.action === "unchanged"
                  ? ` · already saved as ${row.matched_family_code}`
                  : ` · matches ${row.matched_family_code}`)}
              {row.duplicate_of_row && ` · exact copy of row ${row.duplicate_of_row}, skipped`}
            </span>
          </span>
          <span className="flex basis-full flex-wrap items-center gap-x-2 gap-y-0.5 pl-[3.75rem] sm:basis-auto sm:pl-0 sm:pt-0.5">
            {row.note && row.action === "excluded" && (
              <span className="text-xs text-muted">{row.note}</span>
            )}
            {decidable && row.undecided > 0 && (
              <span className="text-xs font-semibold">
                {row.undecided} to decide
              </span>
            )}
            {decidable && row.undecided === 0 && (row.changes.length > 0 || row.match_choice) && (
              <span className="text-xs text-muted">Decided</span>
            )}
            {row.edited_fields.length > 0 && (
              <span className="text-xs text-accent">
                {row.edited_fields.length} corrected
              </span>
            )}
            {row.problems.length > 0 && (
              <span className="text-xs text-warning">
                {row.problems.length} problem{row.problems.length === 1 ? "" : "s"}
              </span>
            )}
            {hasDetail && (
              <span className="text-xs text-muted">{open ? "hide" : "show"}</span>
            )}
          </span>
        </button>

        {row.fields.length > 0 && (
          <button
            onClick={() => setEditing((v) => !v)}
            aria-expanded={editing}
            className="-my-1.5 min-h-10 shrink-0 rounded-full border border-border px-3.5 text-[14px] font-medium text-accent hover:bg-surface-2"
          >
            {editing ? "Close" : "Edit"}
          </button>
        )}
      </div>

      {editing && (
        <div className="sm:pl-12">
          <RowEditor
            importId={importId}
            row={row}
            onUpdated={onUpdated}
            onClose={() => setEditing(false)}
          />
        </div>
      )}

      {open && (
        <div className="mt-2 space-y-2 sm:pl-12">
          {row.action === "needs_decision" && <DuplicateChoice row={row} busy={busy} send={send} />}
          {row.action === "lookalike_in_file" && <PairChoice row={row} busy={busy} send={send} />}

          {row.changes.length > 0 && decidable && (
            <>
              {row.changes.length > 1 && (
                <div className="flex flex-wrap items-center gap-2 text-[14px]">
                  <span className="text-muted">For all {row.changes.length} values:</span>
                  <button onClick={() => all("excel")} disabled={busy} className="min-h-9 rounded-full border border-border px-3 hover:bg-surface-2">
                    Take Excel for all
                  </button>
                  <button onClick={() => all("keep")} disabled={busy} className="min-h-9 rounded-full border border-border px-3 hover:bg-surface-2">
                    Keep database for all
                  </button>
                </div>
              )}
              <ul className="space-y-2">
                {row.changes.map((change) => (
                  <ChangeChoice key={change.field_name} change={change} busy={busy} send={send} type={type} />
                ))}
              </ul>
            </>
          )}

          {error && <p className="text-[14px] text-danger">{error}</p>}
          {row.pair_choice && row.action !== "lookalike_in_file" && (
            <p className="text-[14px] text-muted">
              Looks like row {row.pair_with_row}: you chose{" "}
              {row.pair_choice === "both" ? "to keep both" : `to keep row ${row.pair_choice === "first" ? row.pair_with_row : row.row_number}`}.{" "}
              <button onClick={() => send({ pair: "undo" })} disabled={busy} className="text-accent underline">
                Change
              </button>
            </p>
          )}
          {row.problems.map((problem, i) => (
            <p key={i} className="text-[14px] text-warning">
              {problem.message}
            </p>
          ))}
          {row.match_reasons.length > 0 && (
            <p className="text-xs text-muted">
              Matched because: {row.match_reasons.join("; ")} ({row.match_score}%
              sure)
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function Group({
  action,
  rows,
  importId,
  onUpdated,
  tone,
}: {
  tone: Tone;
  action: RowPreview["action"];
  rows: RowPreview[];
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
}) {
  const waiting = rows.filter((r) => r.undecided > 0).length;
  const [open, setOpen] = useState(
    waiting > 0 ||
      action === "possible_typo" ||
      action === "needs_decision" ||
      action === "lookalike_in_file" ||
      action === "duplicate_in_file",
  );
  if (rows.length === 0) return null;

  return (
    // A card with a coloured left edge; it opens to show its rows.
    <li className={`rounded-lg border border-l-4 border-border bg-bg ${tone.edge}`}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left hover:bg-surface-2"
      >
        <span className="min-w-0 flex-1 text-[15px]">{ACTION_LABELS[action]}</span>
        <span className={`rounded-full px-2 py-0.5 text-[13px] font-semibold tabular-nums ${tone.pill}`}>
          {rows.length}
        </span>
        <Chevron open={open} />
      </button>
      {open && (
        <ul className="mb-3 px-3">
          {rows.map((row) => (
            <Row
              key={row.row_number}
              row={row}
              importId={importId}
              onUpdated={onUpdated}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/** The same words wherever rows repeated inside the sheet are mentioned. */
function repeatsText(count: number): string {
  return count === 1
    ? "1 row is an exact copy of another row in this sheet, so it is skipped."
    : `${count} rows are exact copies of other rows in this sheet, so they are skipped.`;
}

/** Shown instead of the Import button when no row would be written, with the reasons why. */
function NothingToImport({ counts }: { counts: PreviewResult["counts"] }) {
  const n = (action: RowPreview["action"]) => counts[action] ?? 0;
  const s = (count: number) => (count === 1 ? "" : "s");
  const reasons = [
    n("unchanged") > 0 &&
      `${n("unchanged")} famil${n("unchanged") === 1 ? "y is" : "ies are"} already in the database with the same details.`,
    n("duplicate_in_file") > 0 && repeatsText(n("duplicate_in_file")),
    n("excluded") > 0 && `${n("excluded")} row${s(n("excluded"))} you left out.`,
    n("skipped") > 0 && `${n("skipped")} row${s(n("skipped"))} could not be used.`,
  ].filter(Boolean) as string[];

  return (
    <div className="rounded-xl border border-border bg-bg px-4 py-4" role="status">
      <p className="text-[17px] font-semibold">Nothing new to import</p>
      {reasons.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px]">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[15px] text-muted">
        To add or update families, change the sheet and upload it again.
      </p>
    </div>
  );
}

export default function ImportPreview({
  importId,
  onBusyChange,
  onFinished,
  onStartAgain,
  onEditsChange,
}: Props) {
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
      preview.rows.filter((r) => r.edited_fields.length > 0 || r.skipped_by_user).length,
    );
  }, [preview, onEditsChange]);
  useEffect(() => {
    let cancelled = false;
    previewImport(importId)
      .then((data) => !cancelled && setPreview(data))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not build the preview."),
      );
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
      setError(e instanceof Error ? e.message : "The import failed.");
    } finally {
      setImporting(false);
    }
  }

  if (error && !preview) {
    return <p className="text-[17px] text-danger">{error}</p>;
  }
  if (!preview) {
    return <ImportProgress step="checking" importId={importId} />;
  }
  if (importing) {
    // The import checks the rows once more, then saves: the card follows both.
    return <ImportProgress step="checking" importId={importId} />;
  }

  if (result) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
        <h2 className="text-[18px] font-semibold text-accent">Import finished</h2>
        <ul className="mt-3 space-y-1 text-[15px]">
          <li>{result.created} families added</li>
          <li>
            {result.updated} families updated — {result.fields_changed} fields changed,
            with the old values kept
          </li>
          <li>{result.unchanged} already correct</li>
          {result.duplicates_flagged > 0 && (
            <li>{result.duplicates_flagged} duplicate rows in the sheet were not imported</li>
          )}
          {result.excluded > 0 && (
            <li>{result.excluded} rows you left out were not imported</li>
          )}
          {result.fields_corrected > 0 && (
            <li>
              {result.fields_corrected} values you corrected — recorded as changed
              by you, not by the file
            </li>
          )}
          {result.skipped > 0 && <li>{result.skipped} rows could not be used</li>}
          {result.issues_raised > 0 && (
            <li className="text-warning">
              {result.issues_raised} items added to the needs-attention list
            </li>
          )}
        </ul>
        {onStartAgain && (
          <button
            onClick={onStartAgain}
            className="mt-4 w-full rounded-full border border-border px-6 py-3 text-[17px] font-semibold
              hover:bg-surface-2 sm:w-auto"
          >
            Upload another sheet
          </button>
        )}
      </div>
    );
  }

  const sections = SECTIONS.map((section) => ({
    ...section,
    groups: section.actions
      .map((action) => ({ action, rows: preview.rows.filter((r) => r.action === action) }))
      .filter((g) => g.rows.length > 0),
  })).filter((section) => section.groups.length > 0);
  const willWrite = preview.rows.filter(
    (r) =>
      r.action === "create" ||
      r.action === "update" ||
      r.action === "possible_typo" ||
      r.action === "lookalike_in_file" ||
      (r.action === "needs_decision" && r.match_choice !== "leave"),
  ).length;
  const waiting = preview.undecided ?? {};
  const waitingRows = Object.values(waiting).reduce((a, n) => a + n, 0);

  return (
    <div className="rounded-2xl border border-border bg-surface p-4 sm:p-5">
      <h2 className="text-[18px] font-semibold">What will change</h2>
      <p className="mt-1 text-[15px] leading-relaxed text-muted">
        I checked all {preview.total_rows} rows against the families already on record.
        Nothing has been saved yet.
      </p>

      <PreviewColumns preview={preview} onUpdated={setPreview} />

      {sections.map((section) => (
        <section key={section.title} className="mt-6">
          <h3 className="text-[17px] font-semibold">{section.title}</h3>
          <ul className="mt-2 space-y-2">
            {section.groups.map(({ action, rows }) => (
              <Group
                key={action}
                action={action}
                rows={rows}
                importId={importId}
                onUpdated={setPreview}
                tone={section.tone}
              />
            ))}
          </ul>
        </section>
      ))}

      <div className="mt-5 space-y-3 border-t border-border pt-4">
        {error && <p className="text-[15px] text-danger">{error}</p>}
        {willWrite === 0 ? (
          <NothingToImport counts={preview.counts} />
        ) : (
          <>
            <button
              onClick={runImport}
              disabled={importing || waitingRows > 0}
              className="w-full rounded-full bg-accent px-6 py-3 text-[17px] font-semibold text-accent-fg
                disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted sm:w-auto"
            >
              {importing ? "Importing..." : `Import ${willWrite} rows`}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
