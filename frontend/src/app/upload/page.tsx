"use client";

/**
 * Upload a sheet: drop the file, review what would change, save.
 *
 * His sheet always has the same columns, so they are matched by themselves.
 * He is only asked about columns when the sheet has one the system does not
 * know, or is missing a column it needs. Otherwise he goes straight from the
 * file to the review: his sheet next to what is already saved.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import ColumnMapping from "@/components/ColumnMapping";
import ImportPreview from "@/components/ImportPreview";
import ImportProgress from "@/components/ImportProgress";
import { Notice, errorText } from "@/components/ui";
import { IGNORE, confirmMapping, uploadSheet, type UploadResult } from "@/lib/api";
import { classify, formatSize } from "@/lib/files";

/** What the page is doing: the heading and the short line under it change with it. */
const STAGES = [
  { title: "Upload a sheet", intro: "Nothing is saved until you press Save." },
  { title: "Review changes", intro: "" },
  { title: "Saved", intro: "" },
];

const primary =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-accent px-6 text-[16px] font-semibold " +
  "text-accent-fg shadow-sm transition hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed " +
  "disabled:bg-surface-2 disabled:text-muted disabled:shadow-none";
const quiet =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-border bg-surface px-4 " +
  "text-[15px] font-medium transition hover:bg-surface-2 active:scale-[0.98]";

const SheetIcon = ({ size = 24 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    <path d="M14 3v5h5M8.5 12.5h7M8.5 16h7M12 11v7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>
);

/** A thin bar in three parts under the heading: how far along he is, without step names. */
function Progress({ stage }: { stage: number }) {
  return (
    <div className="mt-5 flex items-center gap-3" aria-label={`Part ${stage + 1} of 3`}>
      <div className="flex w-40 gap-1.5 sm:w-52" aria-hidden="true">
        {STAGES.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors ${i <= stage ? "bg-accent" : "bg-border"}`}
          />
        ))}
      </div>
      <span className="text-[13px] font-medium text-muted">{stage + 1} of 3</span>
    </div>
  );
}

/** "Leave this file?" before row corrections are thrown away. "Stay here" has
 *  the focus, so an accidental Enter keeps them; Escape or a click outside too. */
function ConfirmLeave({
  rows,
  onStay,
  onLeave,
}: {
  rows: number;
  onStay: () => void;
  onLeave: () => void;
}) {
  const stayButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    stayButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onStay();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onStay]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-leave-title"
      aria-describedby="confirm-leave-body"
    >
      <button aria-label="Stay here" onClick={onStay} className="absolute inset-0 bg-black/45" tabIndex={-1} />
      <div className="pb-safe relative w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl">
        <h2 id="confirm-leave-title" className="text-[20px] font-semibold leading-tight">
          Leave this file?
        </h2>
        <div id="confirm-leave-body" className="mt-2 space-y-2 text-[16px] leading-relaxed text-muted">
          <p>
            You made {rows === 1 ? "a choice" : "choices"} on {rows} famil{rows === 1 ? "y" : "ies"} in this
            sheet. If you choose another file, {rows === 1 ? "it" : "they"} will be lost.
          </p>
          <p>Nothing has been saved to the families yet.</p>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button ref={stayButton} type="button" onClick={onStay} className={`${quiet} w-full sm:w-auto`}>
            Stay here
          </button>
          <button type="button" onClick={onLeave} className={`${primary} w-full sm:w-auto`}>
            Yes, choose another
          </button>
        </div>
      </div>
    </div>
  );
}

/** Does this sheet need his word on its columns? Only for columns we have no place for,
 *  or a required column that is missing. */
function columnsNeedHim(result: UploadResult): boolean {
  return result.missing_required.length > 0 || result.columns.some((c) => !c.target_key);
}

export default function UploadPage() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [reading, setReading] = useState(false);
  // Share of the file sent so far (0 to 1), for the progress bar.
  const [sent, setSent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [columnsConfirmed, setColumnsConfirmed] = useState(false);
  // While rows are checked or saved there is no leaving the file.
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  // Rows he decided on, corrected or left out. They belong to this upload, so
  // choosing another file loses them: we ask first.
  const [rowEdits, setRowEdits] = useState(0);
  const [askLeave, setAskLeave] = useState(false);
  const [dragging, setDragging] = useState(false);

  const stage = finished ? 2 : upload || reading ? 1 : 0;
  const { title, intro } = STAGES[stage];

  /** Choose another file: straight away, or after a warning if choices would be lost. */
  function leaveFile() {
    if (rowEdits > 0 && !finished) setAskLeave(true);
    else startAgain();
  }

  const onBusyChange = useCallback((value: boolean) => setBusy(value), []);
  const onFinished = useCallback(() => setFinished(true), []);
  const onEditsChange = useCallback((rows: number) => setRowEdits(rows), []);

  async function choose(picked: File | undefined) {
    if (!picked) return;
    setError(null);
    if (classify(picked) !== "excel") {
      setError(`“${picked.name}” is not a spreadsheet. Please choose an Excel file (.xlsx, .xls) or a .csv file.`);
      return;
    }
    setFile(picked);
    setUpload(null);
    setColumnsConfirmed(false);
    setFinished(false);
    setRowEdits(0);
    setReading(true);
    setSent(0);
    try {
      const result = await uploadSheet(picked, setSent);
      // The usual columns: accept the matching as it is and go straight to the review.
      if (!columnsNeedHim(result)) {
        const mapping = Object.fromEntries(
          result.columns.map((c) => [c.source_heading, c.target_key || IGNORE]),
        );
        await confirmMapping(result.import_id, mapping);
        setColumnsConfirmed(true);
      }
      setUpload(result);
    } catch (e) {
      setError(errorText(e));
      setFile(null);
    } finally {
      setReading(false);
    }
  }

  function startAgain() {
    setFile(null);
    setUpload(null);
    setColumnsConfirmed(false);
    setBusy(false);
    setFinished(false);
    setRowEdits(0);
    setAskLeave(false);
    setError(null);
    if (input.current) input.current.value = "";
  }

  return (
    <AppShell plain>
      <header className="mb-8">
        <h1 className="text-[30px] font-semibold leading-tight tracking-tight sm:text-[36px]">{title}</h1>
        {intro && <p className="mt-2 text-[16px] text-muted sm:text-[17px]">{intro}</p>}
        <Progress stage={stage} />
      </header>

      <input
        ref={input}
        type="file"
        accept=".xlsx,.xls,.csv"
        className="sr-only"
        aria-label="Choose a spreadsheet"
        onChange={(e) => choose(e.target.files?.[0])}
      />

      {error && (
        <div className="mb-6">
          <Notice tone="danger" title="That file could not be used">
            {error}
          </Notice>
        </div>
      )}

      {/* ---------- the file ---------- */}
      {!file && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files?.[0]);
          }}
          className={`rounded-2xl border bg-surface p-2 shadow-sm transition ${
            dragging ? "border-accent ring-4 ring-accent/15" : "border-border"
          }`}
        >
          <div
            className={`flex flex-col items-center rounded-xl border-2 border-dashed px-5 py-12 text-center transition sm:py-16 ${
              dragging ? "border-accent bg-accent-soft" : "border-border"
            }`}
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-soft text-accent">
              <SheetIcon size={28} />
            </span>
            {/* Phones cannot drag files, so they only see the button. */}
            <p className="mt-5 text-[19px] font-semibold sm:hidden">Choose your Excel sheet</p>
            <p className="mt-5 hidden text-[19px] font-semibold sm:block">Drop your Excel sheet here</p>
            <button onClick={() => input.current?.click()} className={`${primary} mt-5 w-full sm:w-auto`}>
              Choose a file
            </button>
            <p className="mt-4 text-[14px] text-muted">Excel (.xlsx, .xls) or .csv</p>
          </div>
        </div>
      )}


      {file && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-3 shadow-sm sm:gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <SheetIcon size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[16px] font-semibold">{file.name}</p>
            <p className="text-[14px] text-muted">
              {reading ? "Reading the sheet…" : `${formatSize(file.size)}${upload ? ` · ${upload.row_count} rows` : ""}`}
            </p>
          </div>
          {!reading && !busy && !finished && (
            <button onClick={leaveFile} className={`${quiet} w-full sm:w-auto`}>
              Choose another file
            </button>
          )}
        </div>
      )}

      {reading && <ImportProgress step="sending" sent={sent} />}

      {/* ---------- only when the sheet's columns need his word ---------- */}
      {upload && !columnsConfirmed && (
        <ColumnMapping result={upload} onConfirmed={() => setColumnsConfirmed(true)} />
      )}

      {/* ---------- the review ---------- */}
      {upload && columnsConfirmed && (
        <ImportPreview
          importId={upload.import_id}
          onBusyChange={onBusyChange}
          onFinished={onFinished}
          onStartAgain={startAgain}
          onEditsChange={onEditsChange}
        />
      )}

      {askLeave && (
        <ConfirmLeave
          rows={rowEdits}
          onStay={() => setAskLeave(false)}
          onLeave={startAgain}
        />
      )}
    </AppShell>
  );
}
