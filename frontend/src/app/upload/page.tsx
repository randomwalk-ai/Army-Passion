"use client";

/** Upload a sheet: choose the file, check the columns, check the rows and save. */

import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import ColumnMapping from "@/components/ColumnMapping";
import ImportPreview from "@/components/ImportPreview";
import ImportProgress from "@/components/ImportProgress";
import { Notice, PageHeader, buttonPrimary, buttonSecondary, errorText } from "@/components/ui";
import { uploadSheet, type UploadResult } from "@/lib/api";
import { classify, formatSize } from "@/lib/files";

const STEPS = ["Choose the file", "Check the columns", "Check and save"];

function Steps({
  current,
  onGoTo,
}: {
  current: number;
  /** Go back to a finished step. Null while going back is not allowed. */
  onGoTo: ((index: number) => void) | null;
}) {
  return (
    // On a phone: three columns, number above a short label. Wider: one line.
    <ol className="mb-4 grid grid-cols-3 gap-2 sm:flex sm:gap-6" aria-label="Steps">
      {STEPS.map((label, index) => {
        const done = index < current;
        const active = index === current;
        // A finished step is a button that takes you back to it.
        const clickable = done && onGoTo !== null;
        const Tag = clickable ? "button" : "div";
        return (
          <li key={label} aria-current={active ? "step" : undefined}>
            <Tag
              {...(clickable
                ? { type: "button" as const, onClick: () => onGoTo(index), title: `Go back to “${label}”` }
                : {})}
              className={`flex w-full flex-col items-center gap-1.5 text-center text-[14px] leading-tight sm:flex-row sm:gap-2.5 sm:text-left sm:text-[16px] ${
                active ? "font-semibold" : "text-muted"
              } ${clickable ? "rounded-full hover:text-text hover:underline" : ""}`}
            >
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[15px] font-semibold ${
                done || active ? "bg-accent text-accent-fg" : "bg-surface-2 text-muted"
              }`}
            >
              {done ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M5 12.5l4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : (
                index + 1
              )}
            </span>
            {label}
            </Tag>
          </li>
        );
      })}
    </ol>
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
      <div className="pb-safe relative w-full max-w-md rounded-3xl border border-border bg-bg p-6 shadow-2xl">
        <h2 id="confirm-leave-title" className="text-[22px] font-semibold leading-tight">
          Leave this file?
        </h2>
        <div id="confirm-leave-body" className="mt-2 space-y-2 text-[16px] leading-relaxed text-muted">
          <p>
            You corrected {rows} row{rows === 1 ? "" : "s"} in this sheet. If you go back to choose a
            file, {rows === 1 ? "that correction" : "those corrections"} will be lost.
          </p>
          <p>Nothing has been saved to the families yet.</p>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button ref={stayButton} type="button" onClick={onStay} className={`${buttonSecondary} w-full sm:w-auto`}>
            Stay here
          </button>
          <button type="button" onClick={onLeave} className={`${buttonPrimary} w-full sm:w-auto`}>
            Yes, go back
          </button>
        </div>
      </div>
    </div>
  );
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
  // The column choices last confirmed, so "Back" to step 2 shows them again.
  const [mapping, setMapping] = useState<Record<string, string> | null>(null);
  // While rows are checked or saved, or once saved, there is no going back.
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  // Rows he corrected or left out in step 3. They belong to this upload, so
  // going back to step 1 loses them: we ask first.
  const [rowEdits, setRowEdits] = useState(0);
  const [askLeave, setAskLeave] = useState(false);
  const [dragging, setDragging] = useState(false);

  const step = !upload ? 0 : !columnsConfirmed ? 1 : 2;
  const canGoBack = step > 0 && !reading && !busy && !finished;

  /** Back to step 1: straight away, or after a warning if corrections would be lost. */
  function leaveFile() {
    if (rowEdits > 0 && !finished) setAskLeave(true);
    else startAgain();
  }

  function goTo(index: number) {
    if (index === 0) leaveFile();
    else if (index === 1) {
      setColumnsConfirmed(false);
      setBusy(false);
    }
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
    setMapping(null);
    setFinished(false);
    setRowEdits(0);
    setReading(true);
    setSent(0);
    try {
      setUpload(await uploadSheet(picked, setSent));
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
    setMapping(null);
    setBusy(false);
    setFinished(false);
    setRowEdits(0);
    setAskLeave(false);
    setError(null);
    if (input.current) input.current.value = "";
  }

  return (
    <AppShell>
      <PageHeader
        title="Upload a sheet"
        intro="Add new families or update existing ones from an Excel sheet. Nothing is saved until you have checked it and pressed the final button."
      />

      <Steps current={step} onGoTo={canGoBack ? goTo : null} />

      <div className="mb-6 min-h-11 sm:mb-8">
        {canGoBack && (
          <button
            onClick={() => goTo(step - 1)}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-[16px] font-medium text-accent hover:bg-surface-2"
          >
            <span aria-hidden="true">←</span> Back
          </button>
        )}
      </div>

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

      {/* ---------- step 1 ---------- */}
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
          className={`flex flex-col items-center rounded-3xl border-2 border-dashed px-5 py-10 text-center transition sm:px-6 sm:py-14 ${
            dragging ? "border-accent bg-accent-soft" : "border-border bg-surface"
          }`}
        >
          <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-soft text-accent" aria-hidden="true">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
              <rect x="3.5" y="4" width="17" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
              <path d="M3.5 9.5h17M9.5 9.5V20M3.5 15h17" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </span>
          {/* Phones cannot drag files, so they only see the button. */}
          <p className="mt-5 text-xl font-semibold sm:hidden">Choose your Excel sheet</p>
          <p className="mt-5 hidden text-xl font-semibold sm:block">Drag your Excel sheet here</p>
          <p className="mt-1 hidden text-[16px] text-muted sm:block">or</p>
          <button onClick={() => input.current?.click()} className={`${buttonPrimary} mt-4 w-full sm:mt-3 sm:w-auto`}>
            Choose a file
          </button>
          <p className="mt-4 text-[15px] text-muted">Excel (.xlsx, .xls) or .csv</p>
        </div>
      )}

      {file && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-surface px-4 py-4 sm:gap-4 sm:px-5">
          <span className="text-accent" aria-hidden="true">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <rect x="3.5" y="4" width="17" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
              <path d="M3.5 9.5h17M9.5 9.5V20M3.5 15h17" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[17px] font-medium">{file.name}</p>
            <p className="text-[14px] text-muted">
              {reading ? "Reading the sheet…" : `${formatSize(file.size)}${upload ? ` · ${upload.row_count} rows` : ""}`}
            </p>
          </div>
          <button onClick={leaveFile} className={`${buttonSecondary} w-full sm:w-auto`}>
            Choose a different file
          </button>
        </div>
      )}

      {reading && <ImportProgress step="sending" sent={sent} />}

      {/* ---------- step 2 ---------- */}
      {upload && !columnsConfirmed && (
        <ColumnMapping
          result={upload}
          saved={mapping}
          onConfirmed={(confirmed) => {
            setMapping(confirmed);
            setColumnsConfirmed(true);
          }}
        />
      )}

      {/* ---------- step 3 ---------- */}
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
