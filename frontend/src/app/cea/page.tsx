"use client";

/** CEA: every family checked against the rules; pick one to fill the claim. */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import EligibilityBadge, { STATUS_LOOK, StatusIcon } from "@/components/EligibilityBadge";
import { Notice, PageHeader, Spinner, buttonSecondary, errorText } from "@/components/ui";
import { getCeaEligibility, rupees, type CeaEligibility, type CeaFamily, type CeaStatus } from "@/lib/api";

const TABS: { status: CeaStatus; label: string; hint: string; empty: string }[] = [
  { status: "eligible", label: "Can claim", hint: "Fill the claim now", empty: "No family can claim for this year." },
  { status: "needs_data", label: "Details missing", hint: "Fill a detail first", empty: "No family is missing details." },
  { status: "eligible_later", label: "Can claim later", hint: "A child is too young", empty: "No family is waiting for a child to start school." },
  { status: "not_eligible", label: "Cannot claim", hint: "Nothing to claim", empty: "Every family can claim something." },
];

function FamilyRow({ family, year }: { family: CeaFamily; year: string }) {
  const canFill = family.status === "eligible" || family.status === "needs_data";
  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-border bg-bg p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="text-[18px] font-semibold">{family.nok_name}</p>
          <EligibilityBadge status={family.status} label={family.status_label} small />
        </div>
        <p className="text-[15px] text-muted">
          {family.soldier_name && (
            <>
              w/o {family.soldier_rank ? `${family.soldier_rank} ` : ""}
              {family.soldier_name} ·{" "}
            </>
          )}
          {[family.district, family.state].filter(Boolean).join(", ") || "Place not recorded"} · {family.family_code}
        </p>
        {family.children.length > 0 ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {family.children.map((c, i) => (
              <li
                key={`${c.member_id}-${i}`}
                className="max-w-full rounded-xl bg-surface px-3 py-1.5 text-[15px]"
              >
                <span className={`mr-1 inline-flex align-[-2px] ${STATUS_LOOK[c.status].text}`}>
                  <StatusIcon status={c.status} />
                </span>
                <span className="font-medium">{c.name}</span>
                {c.age !== null && <span className="text-muted">, {c.age}</span>}
                <span className="text-muted"> — {c.status_label.toLowerCase()}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[15px] text-muted">{family.reasons.join(" ")}</p>
        )}
        {/* Tap to see why: hover tooltips do not exist on a phone. */}
        {family.children.length > 0 && (
          <details className="group mt-2">
            <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-1 text-[15px] text-accent [&::-webkit-details-marker]:hidden">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="transition group-open:rotate-90" aria-hidden="true">
                <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Why?
            </summary>
            <ul className="mt-1 space-y-1.5 text-[15px]">
              {family.children.map((c, i) => (
                <li key={`${c.member_id}-why-${i}`} className="rounded-lg bg-surface px-3 py-2">
                  <span className="font-medium">{c.name}:</span>{" "}
                  <span className="text-muted">{[...c.reasons, ...c.to_confirm].join(" ")}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        {family.status === "needs_data" && (
          <p className="mt-2 text-[15px] text-warning">
            {family.children.flatMap((c) => (c.status === "needs_data" ? c.reasons : []))[0] ??
              family.reasons[0]}
          </p>
        )}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 sm:flex-col sm:items-end">
        {family.amount > 0 && (
          <p className="text-[20px] font-semibold tabular-nums">{rupees(family.amount)}</p>
        )}
        {canFill && (
          <Link
            href={`/cea/${family.family_id}?year=${year}`}
            className={`${
              family.status === "eligible" ? "bg-accent text-accent-fg" : "border border-border bg-bg"
            } inline-flex min-h-12 flex-1 items-center justify-center gap-1.5 rounded-full px-5 text-[16px] font-semibold transition hover:opacity-90 sm:min-h-11 sm:flex-none`}
          >
            {family.status === "eligible" ? "Fill claim form" : "Check details"}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        )}
      </div>
    </li>
  );
}

export default function CeaPage() {
  const [year, setYear] = useState<string | undefined>(undefined);
  const [data, setData] = useState<CeaEligibility | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<CeaStatus>("eligible");
  const [search, setSearch] = useState("");
  const [showRules, setShowRules] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // Opened from the Schemes & grants page with a status picked, e.g. /cea?status=needs_data
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("status");
    const match = TABS.find((t) => t.status === wanted);
    if (match) setTab(match.status);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCeaEligibility(year)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(errorText(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [year, attempt]);

  const shown = useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    return data.families.filter(
      (f) =>
        f.status === tab &&
        (!term ||
          [f.nok_name, f.soldier_name, f.family_code, f.district, f.state, ...f.children.map((c) => c.name)]
            .filter(Boolean)
            .some((v) => v!.toLowerCase().includes(term))),
    );
  }, [data, tab, search]);

  const claimTotal = data?.families.filter((f) => f.status === "eligible").reduce((sum, f) => sum + f.amount, 0) ?? 0;

  return (
    <AppShell>
      <PageHeader
        title="CEA claims"
        back={{ href: "/schemes", label: "All schemes & grants" }}
        intro="Children Education Allowance pays for the schooling of the two eldest children of a soldier who died in service. Pick a family to fill in and print their claim."
      />

      {/* ---------- year and rules ---------- */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end">
        <div>
          <label htmlFor="year" className="mb-1.5 block text-[16px] font-medium">
            Academic year
          </label>
          <select
            id="year"
            value={year ?? data?.academic_year ?? ""}
            onChange={(e) => setYear(e.target.value)}
            className="w-full rounded-xl border border-border bg-bg px-4 py-3 text-[17px] outline-none focus:border-accent focus:ring-4 focus:ring-accent/15 sm:w-56"
          >
            {data?.years.map((y) => (
              <option key={y.label} value={y.label}>
                {y.label}
                {y.is_default ? " (last year — claim now)" : ""}
              </option>
            ))}
          </select>
        </div>
        <button onClick={() => setShowRules((v) => !v)} aria-expanded={showRules} className="min-h-11 self-start text-left text-[16px] text-accent underline sm:self-auto sm:pb-1">
          {showRules ? "Hide the rules" : "What are the rules?"}
        </button>
      </div>

      {showRules && data && (
        <div className="mb-6 rounded-2xl border border-border bg-surface p-4 sm:p-5">
          <p className="text-[17px] font-semibold">What we check</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[16px] text-muted">
            {data.rules_summary.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="mt-3 text-[14px] text-muted">
            From the CEA circular for wards of physical casualties. The claim is sent after the academic year ends.
          </p>
        </div>
      )}

      {error && (
        <div className="space-y-3">
          <Notice tone="danger" title="The list could not be loaded">
            {error}
          </Notice>
          <button onClick={() => setAttempt((n) => n + 1)} className={buttonSecondary}>
            Try again
          </button>
        </div>
      )}

      {loading && !data && <Spinner label="Checking every family…" />}

      {data && (
        <>
          {/* ---------- summary ---------- */}
          <div className="mb-5 rounded-2xl border border-accent bg-accent-soft px-4 py-3.5 sm:mb-6 sm:px-5 sm:py-4">
            <p className="text-[17px]">
              <span className="font-semibold">{data.counts.eligible} families</span> can claim for {data.academic_year}, worth about{" "}
              <span className="font-semibold">{rupees(claimTotal)}</span> in all.
              {data.counts.needs_data > 0 && (
                <> {data.counts.needs_data} more need a detail filled in first.</>
              )}
            </p>
          </div>

          {/* ---------- tabs and search ---------- */}
          <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            {/* Four answers as four big tiles: two by two on a phone, one row when wide. */}
            <div role="tablist" aria-label="Show families who" className="grid grid-cols-2 gap-2.5 lg:flex-1 lg:grid-cols-4">
              {TABS.map((t) => {
                const selected = tab === t.status;
                return (
                  <button
                    key={t.status}
                    role="tab"
                    aria-selected={selected}
                    onClick={() => setTab(t.status)}
                    className={`flex min-h-[5.5rem] flex-col items-start rounded-2xl border-2 px-3.5 py-3 text-left transition ${
                      selected
                        ? `${STATUS_LOOK[t.status].tile} border-current ${STATUS_LOOK[t.status].text}`
                        : "border-border bg-bg hover:bg-surface-2"
                    }`}
                  >
                    <span className={`flex items-center gap-1.5 text-[15px] font-semibold ${STATUS_LOOK[t.status].text}`}>
                      <StatusIcon status={t.status} size={16} />
                      {t.label}
                    </span>
                    <span className="mt-0.5 text-[28px] font-semibold leading-tight tabular-nums text-text">
                      {data.counts[t.status]}
                    </span>
                    <span className="text-[13px] text-muted">{t.hint}</span>
                  </button>
                );
              })}
            </div>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search a name, place or code"
              aria-label="Search families"
              className="min-h-12 w-full rounded-full border border-border bg-bg px-5 text-[16px] outline-none focus:border-accent focus:ring-4 focus:ring-accent/15 lg:w-72 lg:shrink-0"
            />
          </div>

          <div className={loading ? "opacity-50 transition" : "transition"}>
            {shown.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-border px-5 py-10 text-center text-[17px] text-muted">
                {search ? `No family matches “${search}”.` : TABS.find((t) => t.status === tab)!.empty}
              </p>
            ) : (
              <ul className="space-y-3">
                {shown.map((f) => (
                  <FamilyRow key={f.family_id} family={f} year={data.academic_year} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
