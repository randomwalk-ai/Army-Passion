"use client";

/** The progress card shown while a sheet is sent, checked and saved.
 *
 *  Three steps: Sending → Checking → Saving. The current one shows a big
 *  percentage, a moving bar, "420 of 997 rows" and roughly how long is left.
 *  For checking and saving it asks the server once a second how far it has
 *  got; for sending it is given the share of the file already sent.
 */

import { useEffect, useRef, useState } from "react";
import { getImportProgress, type ImportProgress as Progress } from "@/lib/api";

export type ProgressStep = "sending" | "checking" | "saving";

const STEPS: { key: ProgressStep; label: string }[] = [
  { key: "sending", label: "Sending" },
  { key: "checking", label: "Checking" },
  { key: "saving", label: "Saving" },
];

const TITLES: Record<ProgressStep, string> = {
  sending: "Sending your sheet",
  checking: "Checking each row against the families on record",
  saving: "Saving the families",
};

/** A short line that changes every few seconds, so a long wait never feels stuck. */
const NOTES: Record<ProgressStep, string[]> = {
  sending: ["Uploading the file", "Reading the column headings", "Working out what each column means"],
  checking: [
    "Looking for families already on record",
    "Spotting the same person twice in the sheet",
    "Checking phone numbers and dates",
    "Nothing is saved at this step",
  ],
  saving: [
    "Adding the families",
    "Adding their children",
    "Keeping the old value of every change",
    "Noting anything that needs your attention",
  ],
};

function timeLeft(seconds: number | null): string | null {
  if (seconds === null) return null;
  if (seconds < 5) return "almost done";
  if (seconds < 60) return `about ${Math.ceil(seconds / 5) * 5} seconds left`;
  const minutes = Math.round(seconds / 60);
  return `about ${minutes} minute${minutes === 1 ? "" : "s"} left`;
}

type Props = {
  /** Which step is running. For "checking" and "saving" the server reports the
   *  real step (an import checks first, then saves), so this is a starting point. */
  step: ProgressStep;
  /** For checking and saving: the upload whose progress to ask about. */
  importId?: number;
  /** For sending: 0 to 1, the share of the file already sent. */
  sent?: number;
};

export default function ImportProgress({ step, importId, sent }: Props) {
  const [server, setServer] = useState<Progress | null>(null);
  const [noteIndex, setNoteIndex] = useState(0);
  const startedAt = useRef(Date.now());

  // Ask the server how far along it is, once a second.
  useEffect(() => {
    if (importId === undefined || step === "sending") return;
    let stopped = false;
    const ask = () =>
      getImportProgress(importId)
        .then((p) => !stopped && p.stage && setServer(p))
        .catch(() => {});
    ask();
    const timer = window.setInterval(ask, 1000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [importId, step]);

  // The changing line under the bar.
  useEffect(() => {
    const timer = window.setInterval(() => setNoteIndex((i) => i + 1), 3500);
    return () => window.clearInterval(timer);
  }, []);

  const current: ProgressStep = step === "sending" ? "sending" : (server?.stage ?? step);
  let percent: number | null = null;
  let detail: string | null = null;
  let remaining: string | null = null;

  if (current === "sending" && sent !== undefined) {
    percent = Math.round(sent * 100);
    // Once the file is sent, the server still reads it: say so rather than sit at 100%.
    detail = sent >= 1 ? "File sent. Reading the rows…" : "Sending the file";
  } else if (server && server.stage === current) {
    percent = server.percent;
    detail = `${server.done.toLocaleString("en-IN")} of ${server.total.toLocaleString("en-IN")} rows`;
    remaining = timeLeft(server.seconds_left);
    // Every row is through, but the last group is still being written.
    if (current === "saving" && server.done >= server.total) {
      detail = "Finishing up…";
      remaining = "a few seconds";
    }
  }

  const stepIndex = STEPS.findIndex((s) => s.key === current);
  const notes = NOTES[current];
  const elapsed = Math.round((Date.now() - startedAt.current) / 1000);

  return (
    <section
      className="rounded-2xl border border-border bg-surface p-5 sm:p-6"
      aria-live="polite"
      aria-busy="true"
    >
      {/* The three steps */}
      <ol className="mb-5 flex items-center gap-2 text-[14px]" aria-label="Progress">
        {STEPS.map((s, index) => {
          const done = index < stepIndex;
          const active = index === stepIndex;
          return (
            <li key={s.key} className="flex flex-1 items-center gap-2">
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold transition-colors ${
                  done
                    ? "bg-accent text-accent-fg"
                    : active
                      ? "progress-pulse bg-accent text-accent-fg"
                      : "bg-surface-2 text-muted"
                }`}
              >
                {done ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M5 12.5l4.5 4.5L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  index + 1
                )}
              </span>
              <span className={active ? "font-semibold" : "text-muted"}>{s.label}</span>
              {index < STEPS.length - 1 && (
                <span
                  className={`h-0.5 flex-1 rounded-full ${done ? "bg-accent" : "bg-surface-2"}`}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>

      {/* Title and the big number */}
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-[18px] font-semibold leading-snug sm:text-[20px]">{TITLES[current]}</h2>
        <p className="shrink-0 text-[34px] font-semibold leading-none tabular-nums text-accent sm:text-[40px]">
          {percent === null ? "…" : `${percent}%`}
        </p>
      </div>

      {/* The bar */}
      <div
        className="relative mt-4 h-3.5 overflow-hidden rounded-full bg-surface-2"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
        aria-label={TITLES[current]}
      >
        {percent === null ? (
          <div className="progress-indeterminate absolute inset-y-0 w-2/5 rounded-full bg-accent/70" />
        ) : (
          <div
            className="progress-shine h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${Math.max(percent, 3)}%` }}
          />
        )}
      </div>

      {/* Rows done, time left */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[15px]">
        <span className="font-medium">{detail ?? "Getting started…"}</span>
        <span className="text-muted">
          {remaining ?? (elapsed >= 3 ? `${elapsed} seconds so far` : "")}
        </span>
      </div>

      {/* The changing line */}
      <p key={noteIndex} className="mt-4 flex items-center gap-2 text-[14px] text-muted">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
        {notes[noteIndex % notes.length]}…
      </p>
    </section>
  );
}
