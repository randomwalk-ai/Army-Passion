"use client";

/** Home: the numbers that matter, the families table, and the things he can do. */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import FamilyTable from "@/components/FamilyTable";
import { Notice, buttonSecondary, errorText } from "@/components/ui";
import { getDashboard, type Stat } from "@/lib/api";
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

function StatTile({ stat, large }: { stat: Stat; large: boolean }) {
  const attention = stat.tone === "attention" && stat.value > 0;
  const body = (
    <>
      <p className={`font-medium leading-snug text-muted ${large ? "text-[16px] sm:text-[17px]" : "text-[15px]"}`}>{stat.label}</p>
      <p
        className={`mt-1 font-semibold tabular-nums tracking-tight ${large ? "text-4xl sm:text-6xl" : "text-3xl sm:text-4xl"}`}
      >
        {stat.value.toLocaleString("en-IN")}
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
  const classes = `block min-w-0 rounded-2xl border bg-surface p-4 sm:p-6 ${
    attention ? "border-warning/50" : "border-border"
  }`;
  return stat.href ? (
    <Link href={stat.href} className={`${classes} transition hover:border-accent hover:shadow-sm`}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}

function SkeletonTiles() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4" aria-hidden="true">
      {[0, 1].map((i) => (
        <div key={i} className="h-32 animate-pulse rounded-2xl bg-surface sm:h-40" />
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

  const [main, rest] = stats ? [stats.slice(0, 2), stats.slice(2)] : [[], []];

  return (
    <AppShell>
      <div className="mb-6 sm:mb-8">
        <p className="text-[15px] text-muted sm:text-[16px]">{today()}</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{greeting()}, {CURRENT_USER.name.split(" ")[0]}</h1>
      </div>

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
              {main.map((s) => (
                <StatTile key={s.key} stat={s} large />
              ))}
            </div>
            {rest.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:mt-4 sm:gap-4 lg:grid-cols-3">
                {rest.map((s) => (
                  <StatTile key={s.key} stat={s} large={false} />
                ))}
              </div>
            )}
          </>
        )}
      </section>

      {/* ---------- the data itself ---------- */}
      <section aria-labelledby="families" className="mt-10 sm:mt-12">
        <h2 id="families" className="mb-3 text-xl font-semibold">
          Families
        </h2>
        <FamilyTable compact />
      </section>

      {/* ---------- what he can do ---------- */}
      <section aria-labelledby="actions" className="mt-10 sm:mt-12">
        <h2 id="actions" className="mb-4 text-xl font-semibold">
          What would you like to do?
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {ACTIONS.map((a) => {
            const inner = (
              <>
                <span
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${
                    a.href ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted"
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
                className="group flex gap-4 rounded-2xl border border-border bg-bg p-4 transition sm:p-5
                  hover:border-accent hover:bg-surface hover:shadow-sm"
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
