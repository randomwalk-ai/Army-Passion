"use client";

/** Home: the numbers that matter, the families table, and the things he can do. */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import { Contours, StarMark, Tricolour, useCountUp } from "@/components/Decor";
import FamilyTable from "@/components/FamilyTable";
import ProfileCurve from "@/components/ProfileCurve";
import { Notice, buttonSecondary, errorText } from "@/components/ui";
import { deleteAllData, getDashboard, getResetStatus, type Stat } from "@/lib/api";
import { CURRENT_USER } from "@/lib/currentUser";

function greeting(): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(
      new Date(),
    ),
  );
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function today(): string {
  return new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date());
}

const ACTIONS = [
  {
    href: "/upload",
    title: "Upload a sheet",
    body: "Add or update many families at once from an Excel sheet. You check everything before it is saved.",
    icon: "M12 16V4m0 0L7 9m5-5l5 5M5 20h14",
  },
  {
    href: "/families/new",
    title: "Add a family",
    body: "Type in one family on a simple form. Only the two names are needed to start.",
    icon: "M12 5v14M5 12h14",
  },
  {
    href: "/schemes",
    title: "Schemes & grants",
    body: "See what every family can claim, scheme by scheme, and who needs a detail filled in first.",
    icon: "M9 12l2 2 4-4M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z",
  },
  {
    href: "/cea",
    title: "CEA claims",
    body: "See who can claim Children Education Allowance, and print a filled-in claim form.",
    icon: "M4 8l8-4 8 4-8 4-8-4zm3 2v5c0 1.5 2.5 3 5 3s5-1.5 5-3v-5",
  },
  {
    href: null,
    title: "Voice notes",
    body: "Record a call and the details are filled in for you.",
    icon: "M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v3",
  },
];

function StatTile({ stat, large, index }: { stat: Stat; large: boolean; index: number }) {
  const attention = stat.tone === "attention" && stat.value > 0;
  const shown = useCountUp(stat.value);
  const body = (
    <>
      <p className={`font-medium leading-snug text-muted ${large ? "text-[16px] sm:text-[17px]" : "text-[15px]"}`}>{stat.label}</p>
      <p
        className={`mt-1 font-semibold tabular-nums tracking-tight ${large ? "text-4xl sm:text-6xl" : "text-3xl sm:text-4xl"}`}
      >
        {shown.toLocaleString("en-IN")}
      </p>
      {stat.hint && (
        <p className="mt-2 flex items-start gap-1.5 text-[14px] leading-snug text-muted sm:text-[15px]">
          {attention && (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="mt-0.5 shrink-0 text-warning" aria-hidden="true">
              <path d="M12 3l10 18H2L12 3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <path d="M12 10v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="12" cy="17.2" r="1.1" fill="currentColor" />
            </svg>
          )}
          {attention && <span className="sr-only">Needs attention:</span>}
          {stat.hint}
        </p>
      )}
    </>
  );
  // A thin bar down the left: olive, or brass when something needs attention.
  const classes = `rise relative block min-w-0 overflow-hidden rounded-2xl border bg-surface p-4 pl-5 sm:p-6 sm:pl-7
    before:absolute before:inset-y-0 before:left-0 before:w-1 ${
    attention ? "border-warning/50 before:bg-brass" : "border-border before:bg-accent/70"
  }`;
  const style = { "--i": index } as React.CSSProperties;
  return stat.href ? (
    <Link
      href={stat.href}
      style={style}
      className={`${classes} transition hover:-translate-y-0.5 hover:border-accent hover:shadow-md`}
    >
      {body}
    </Link>
  ) : (
    <div style={style} className={classes}>
      {body}
    </div>
  );
}

/** A section title with a small brass star in front. */
function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="mb-4 flex items-center gap-2.5 text-xl font-semibold">
      <span className="text-brass">
        <StarMark size={16} />
      </span>
      {children}
    </h2>
  );
}

/** "Are you sure?" before emptying the database. Cancel has the focus, so an
 *  accidental Enter does nothing; Escape or a click outside also cancels. */
function ConfirmDelete({
  families,
  deleting,
  onConfirm,
  onCancel,
}: {
  families: number | null;
  deleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !deleting && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [deleting, onCancel]);

  const what =
    families === null
      ? "every family"
      : `all ${families.toLocaleString("en-IN")} ${families === 1 ? "family" : "families"}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-delete-title"
      aria-describedby="confirm-delete-body"
    >
      <button
        aria-label="Cancel"
        onClick={() => !deleting && onCancel()}
        className="absolute inset-0 bg-black/45"
        tabIndex={-1}
      />
      <div className="pb-safe relative w-full max-w-md rounded-3xl border border-border bg-bg p-6 shadow-2xl">
        <span
          className="flex h-12 w-12 items-center justify-center rounded-2xl bg-danger/15 text-danger"
          aria-hidden="true"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path
              d="M5 7h14M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h2 id="confirm-delete-title" className="mt-4 text-[22px] font-semibold leading-tight">
          Delete all data?
        </h2>
        <div id="confirm-delete-body" className="mt-2 space-y-2 text-[16px] leading-relaxed text-muted">
          <p>
            This removes {what}, with their children, applications, documents, call notes, chats and
            history.
          </p>
          <p>User accounts and the list of schemes are kept.</p>
          <p className="font-semibold text-danger">This cannot be undone.</p>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            ref={cancelButton}
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className={`${buttonSecondary} w-full sm:w-auto`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-danger px-6 py-3
              text-[17px] font-semibold text-bg transition hover:opacity-90 disabled:cursor-wait
              disabled:opacity-60 sm:w-auto"
          >
            {deleting ? "Deleting…" : "Yes, delete everything"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SkeletonTiles() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4" aria-hidden="true">
      {[0, 1].map((i) => (
        <div key={i} className="shimmer h-32 rounded-2xl border border-border sm:h-40" />
      ))}
    </div>
  );
}

export default function Home() {
  const [stats, setStats] = useState<Stat[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getDashboard()
      .then((d) => setStats(d.stats))
      .catch((e) => setError(errorText(e)));
  }, []);

  useEffect(load, [load]);

  // "Delete all data": shown only when the server allows it (the demo site).
  const [resetEnabled, setResetEnabled] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const closeConfirm = useCallback(() => setConfirming(false), []);
  // Changing this remounts the families table, so it reloads (empty) after a delete.
  const [tableKey, setTableKey] = useState(0);

  useEffect(() => {
    getResetStatus()
      .then((s) => setResetEnabled(s.enabled))
      .catch(() => setResetEnabled(false));
  }, []);

  async function removeEverything() {
    setDeleting(true);
    setDeleteError(null);
    setDeleted(null);
    try {
      const { families_removed } = await deleteAllData();
      setConfirming(false);
      setDeleted(families_removed);
      load();
      setTableKey((k) => k + 1);
    } catch (e) {
      setConfirming(false);
      setDeleteError(errorText(e));
    } finally {
      setDeleting(false);
    }
  }

  const [main, rest] = stats ? [stats.slice(0, 2), stats.slice(2)] : [[], []];

  return (
    <AppShell>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3 sm:mb-8">
        <div>
          <p className="text-[15px] text-muted sm:text-[16px]">{today()}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{greeting()}, {CURRENT_USER.name.split(" ")[0]}</h1>
        </div>
        {resetEnabled && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={deleting}
            className="inline-flex items-center gap-2 rounded-full border border-danger/60 bg-bg px-4 py-2.5
              text-[15px] font-medium text-danger transition hover:bg-danger hover:text-bg
              disabled:cursor-wait disabled:opacity-60"
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M5 7h14M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {deleting ? "Deleting…" : "Delete all data"}
          </button>
        )}
      </div>
      {/* The banner: deep olive, map lines and the tricolour along the top. */}
      <header className="olive-panel rise relative isolate mb-6 overflow-hidden rounded-3xl px-5 pb-6 pt-7 shadow-sm sm:mb-8 sm:px-8 sm:pb-8 sm:pt-9">
        <Tricolour />
        <Contours />
        <p className="text-[12px] font-semibold uppercase tracking-[0.22em] text-accent sm:text-[13px]">Jai Hind</p>
        <h1 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
          {greeting()}, {CURRENT_USER.name.split(" ")[0]}
        </h1>
        <p className="mt-2 max-w-2xl text-[16px] text-muted sm:text-[17px]">{today()}</p>
        <p className="mt-4 max-w-2xl text-[16px] leading-relaxed sm:text-[17px]">
          Every family of the fallen, looked after.
        </p>
      </header>

      {confirming && (
        <ConfirmDelete
          families={stats?.find((s) => s.key === "families")?.value ?? null}
          deleting={deleting}
          onConfirm={removeEverything}
          onCancel={closeConfirm}
        />
      )}

      {deleted !== null && (
        <div className="mb-6">
          <Notice tone="success" title="All data deleted" onClose={() => setDeleted(null)}>
            {deleted.toLocaleString("en-IN")} {deleted === 1 ? "family was" : "families were"} removed.
            The database is empty and ready for a new sheet.
          </Notice>
        </div>
      )}
      {deleteError && (
        <div className="mb-6">
          <Notice tone="danger" title="Could not delete the data" onClose={() => setDeleteError(null)}>
            {deleteError}
          </Notice>
        </div>
      )}

      {/* ---------- the numbers ---------- */}
      <section aria-labelledby="numbers">
        <h2 id="numbers" className="sr-only">
          At a glance
        </h2>
        {error ? (
          <div className="space-y-3">
            <Notice tone="danger" title="The numbers could not be loaded">
              {error}
            </Notice>
            <button onClick={load} className={buttonSecondary}>
              Try again
            </button>
          </div>
        ) : !stats ? (
          <SkeletonTiles />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:gap-4">
              {main.map((s, i) => (
                <StatTile key={s.key} stat={s} large index={i} />
              ))}
            </div>
            {rest.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:mt-4 sm:gap-4 lg:grid-cols-3">
                {rest.map((s, i) => (
                  <StatTile key={s.key} stat={s} large={false} index={i + 2} />
                ))}
              </div>
            )}
          </>
        )}
      </section>

      {/* ---------- how complete the profiles are ---------- */}
      <section aria-label="How complete are the profiles?" className="mt-8 sm:mt-10">
        <ProfileCurve />
      </section>

      {/* ---------- the data itself ---------- */}
      <section aria-labelledby="families" className="mt-10 sm:mt-12">
        <SectionHeading id="families">Families</SectionHeading>
        <FamilyTable compact />
      </section>

      {/* ---------- what he can do ---------- */}
      <section aria-labelledby="actions" className="mt-10 sm:mt-12">
        <SectionHeading id="actions">What would you like to do?</SectionHeading>
        <div className="grid gap-4 sm:grid-cols-2">
          {ACTIONS.map((a, index) => {
            const inner = (
              <>
                <span
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl transition ${
                    a.href
                      ? "bg-accent-soft text-accent group-hover:bg-accent group-hover:text-accent-fg"
                      : "bg-surface-2 text-muted"
                  }`}
                  aria-hidden="true"
                >
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                    <path d={a.icon} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[18px] font-semibold sm:text-[19px]">
                    {a.title}
                    {!a.href && (
                      <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-muted">
                        Coming soon
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-[16px] leading-relaxed text-muted">{a.body}</span>
                </span>
              </>
            );
            return a.href ? (
              <Link
                key={a.title}
                href={a.href}
                style={{ "--i": index } as React.CSSProperties}
                className="rise group flex gap-4 rounded-2xl border border-border bg-surface p-4 transition sm:p-5
                  hover:-translate-y-0.5 hover:border-accent hover:shadow-md"
              >
                {inner}
                <svg
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  className="mt-3 shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-accent"
                  aria-hidden="true"
                >
                  <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
            ) : (
              <div
                key={a.title}
                aria-disabled="true"
                className="flex gap-4 rounded-2xl border border-dashed border-border bg-bg p-4 opacity-80 sm:p-5"
              >
                {inner}
              </div>
            );
          })}
        </div>
      </section>
    </AppShell>
  );
}
