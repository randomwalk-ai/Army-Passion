"use client";

import { useEffect, useState } from "react";
import PreviewColumns from "@/components/PreviewColumns";
import RowEditor from "@/components/RowEditor";
import {
  commitImport,
  previewImport,
  type CommitResult,
  type PreviewResult,
  type RowPreview,
} from "@/lib/api";

type Props = { importId: number };

const ACTION_LABELS: Record<RowPreview["action"], string> = {
  create: "New families",
  update: "Updates to families you already have",
  unchanged: "Already correct, nothing changes",
  needs_decision: "Might already exist — needs you to decide",
  duplicate_in_file: "The same person twice in this sheet",
  skipped: "Cannot be used",
  excluded: "You left these out",
};

const ACTION_ORDER: RowPreview["action"][] = [
  "create",
  "update",
  "needs_decision",
  "duplicate_in_file",
  "unchanged",
  "excluded",
  "skipped",
];

function Row({
  row,
  importId,
  onUpdated,
}: {
  row: RowPreview;
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
}) {
  // "Might already exist" rows are opened by default: the whole point of that
  // group is to decide, and the reasons are what you decide on.
  const [open, setOpen] = useState(row.action === "needs_decision");
  const [editing, setEditing] = useState(false);
  const who = row.widow_name || row.soldier_name || "(no name)";
  // Match reasons count as detail too. Without them a "needs you to decide"
  // row could not be opened at all, hiding the very thing you need to see.
  const hasDetail =
    row.changes.length > 0 ||
    row.problems.length > 0 ||
    row.match_reasons.length > 0;

  return (
    <li className="border-t border-border py-2.5">
      <div className="flex items-start gap-3">
        <button
          onClick={() => hasDetail && setOpen((v) => !v)}
          className={`flex min-w-0 flex-1 items-start gap-3 text-left ${
            hasDetail ? "" : "cursor-default"
          }`}
        >
          <span className="w-12 shrink-0 pt-0.5 text-xs text-muted">
            Row {row.row_number}
          </span>
          <span className="min-w-0 flex-1">
            <span
              className={`block truncate text-[15px] font-medium ${
                row.skipped_by_user ? "text-muted line-through" : ""
              }`}
            >
              {who}
            </span>
            <span className="block truncate text-xs text-muted">
              {row.district}
              {row.matched_family_code && ` · matches ${row.matched_family_code}`}
              {row.duplicate_of_row && ` · same as row ${row.duplicate_of_row}`}
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-2 pt-0.5">
            {row.edited_fields.length > 0 && (
              <span className="text-xs text-accent">
                {row.edited_fields.length} corrected
              </span>
            )}
            {row.changes.length > 0 && (
              <span className="text-xs text-muted">
                {row.changes.length} change{row.changes.length === 1 ? "" : "s"}
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
            className="shrink-0 pt-0.5 text-xs text-accent underline"
          >
            {editing ? "close" : "edit"}
          </button>
        )}
      </div>

      {editing && (
        <div className="pl-12">
          <RowEditor
            importId={importId}
            row={row}
            onUpdated={onUpdated}
            onClose={() => setEditing(false)}
          />
        </div>
      )}

      {open && (
        <div className="mt-2 space-y-2 pl-12">
          {row.changes.length > 0 && (
            <table className="w-full text-[14px]">
              <tbody>
                {row.changes.map((change) => (
                  <tr key={change.field_name} className="align-top">
                    <td className="py-1 pr-3 text-muted">{change.label}</td>
                    <td className="py-1 pr-3 text-muted line-through">
                      {change.old_value ?? "(blank)"}
                    </td>
                    <td className="py-1 font-medium">{change.new_value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
          {row.action === "needs_decision" && (
            <p className="text-[14px] text-warning">
              Not sure enough to treat as the same family. If you import, this is
              added as a separate record and flagged for you to check later —
              nothing is merged.
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
}: {
  action: RowPreview["action"];
  rows: RowPreview[];
  importId: number;
  onUpdated: (preview: PreviewResult) => void;
}) {
  const [open, setOpen] = useState(
    action === "needs_decision" || action === "duplicate_in_file",
  );
  if (rows.length === 0) return null;

  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-lg bg-surface-2 px-3 py-2.5 text-left"
      >
        <span className="text-[15px] font-medium">
          {rows.length} — {ACTION_LABELS[action]}
        </span>
        <span className="text-xs text-muted">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <ul className="mt-1">
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
    </div>
  );
}

export default function ImportPreview({ importId }: Props) {
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

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
    return <p className="text-[17px] text-muted">Checking against the families on record...</p>;
  }

  if (result) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-5">
        <h2 className="text-[17px] font-semibold text-accent">Import finished</h2>
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
          {result.needs_decision > 0 && (
            <li className="text-warning">
              {result.needs_decision} may be families you already have — added, and
              flagged for you to decide
            </li>
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
      </div>
    );
  }

  const grouped = ACTION_ORDER.map((action) => ({
    action,
    rows: preview.rows.filter((r) => r.action === action),
  }));
  const willWrite =
    (preview.counts.create ?? 0) +
    (preview.counts.update ?? 0) +
    (preview.counts.needs_decision ?? 0);

  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h2 className="text-[17px] font-semibold">What will change</h2>
      <p className="mt-1 text-[15px] leading-relaxed text-muted">
        I checked all {preview.total_rows} rows against the families already on record.
        Nothing has been saved yet.
      </p>

      <PreviewColumns preview={preview} onUpdated={setPreview} />

      {grouped.map(({ action, rows }) => (
        <Group
          key={action}
          action={action}
          rows={rows}
          importId={importId}
          onUpdated={setPreview}
        />
      ))}

      <div className="mt-5 space-y-3 border-t border-border pt-4">
        {error && <p className="text-[15px] text-danger">{error}</p>}
        <p className="text-[15px] text-muted">
          {willWrite} row{willWrite === 1 ? "" : "s"} will be written. Every change
          keeps the old value, so this can be traced back.
        </p>
        <button
          onClick={runImport}
          disabled={importing || willWrite === 0}
          className="rounded-full bg-accent px-5 py-2.5 text-[15px] font-medium text-accent-fg
            disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
        >
          {importing ? "Importing..." : `Import ${willWrite} rows`}
        </button>
      </div>
    </div>
  );
}
