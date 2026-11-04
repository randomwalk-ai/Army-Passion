"use client";

/**
 * Schemes & grants: every family checked against every scheme and grant.
 *
 * The schemes come from the server's list (app/services/eligibility.py), so a
 * new scheme shows up here as one more card, with the same four answers.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { STATUS_LOOK, StatusIcon } from "@/components/EligibilityBadge";
import FamilyEligibility from "@/components/FamilyEligibility";
import { Notice, PageHeader, buttonSecondary, errorText } from "@/components/ui";
import {
  getEligibilityOverview,
  rupees,
  searchFamilies,
  type FamilySearchItem,
  type SchemeOverview,
} from "@/lib/api";

const HINTS: Record<string, string> = {
  eligible: "Ready to fill the claim",
  needs_data: "A detail to fill in first",
  eligible_later: "Not yet, but will be",
  not_eligible: "Nothing to claim",
};

function SchemeCard({ scheme }: { scheme: SchemeOverview }) {
  const total = scheme.families_checked || 1;
  const eligible = scheme.counts.find((c) => c.status === "eligible")?.count ?? 0;
  return (
    <section className="rounded-3xl border border-border bg-surface p-4 sm:p-6" aria-labelledby={`scheme-${scheme.code}`}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1 basis-64">
          <h2 id={`scheme-${scheme.code}`} className="text-[22px] font-semibold leading-tight">
            {scheme.name}
          </h2>
          <p className="mt-1 text-[16px] leading-relaxed text-muted">{scheme.description}</p>
        </div>
        <span className="rounded-full bg-bg px-3 py-1 text-[14px] font-medium text-muted">{scheme.period}</span>
      </div>

      {/* The whole picture in one line: how the families split. */}
      <div className="mt-5 flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
        {scheme.counts
          .filter((c) => c.count > 0)
          .map((c) => (
            <span
              key={c.status}
              className={`${STATUS_LOOK[c.status].bar} first:rounded-l-full last:rounded-r-full`}
              style={{ flexGrow: c.count, flexBasis: 0 }}
            />
          ))}
      </div>
      <p className="sr-only">
        {scheme.counts.map((c) => `${c.label}: ${c.count}`).join(", ")} of {scheme.families_checked} families.
      </p>

      <ul className="mt-4 grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4">
        {scheme.counts.map((c) => (
          <li key={c.status}>
            <Link
              href={`${scheme.href}?status=${c.status}`}
              className={`flex h-full flex-col rounded-2xl border p-3.5 transition hover:border-accent hover:shadow-sm sm:p-4 ${STATUS_LOOK[c.status].tile}`}
            >
              <span className={`flex items-center gap-1.5 text-[15px] font-semibold ${STATUS_LOOK[c.status].text}`}>
                <StatusIcon status={c.status} size={16} />
                {c.label}
              </span>
              <span className="mt-1 text-3xl font-semibold tabular-nums tracking-tight sm:text-4xl">
                {c.count.toLocaleString("en-IN")}
              </span>
              <span className="mt-1 text-[14px] leading-snug text-muted">
                {Math.round((c.count / total) * 100)}% · {HINTS[c.status]}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="mt-5 flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center">
        <p className="mr-auto text-[16px]">
          {eligible > 0 ? (
            <>
              <span className="font-semibold">{eligible} families</span> can claim about{" "}
              <span className="font-semibold tabular-nums">{rupees(scheme.amount_total)}</span> in all.
            </>
          ) : (
            "No family can claim right now."
          )}
        </p>
        <Link
          href={scheme.href}
          className="inline-flex min-h-12 items-center justify-center gap-1.5 rounded-full bg-accent px-5 text-[16px] font-semibold text-accent-fg hover:opacity-90"
        >
          See the families
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>
    </section>
  );
}

/** Pick one family and see every scheme's answer for it. */
function OneFamily() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FamilySearchItem[]>([]);
  const [picked, setPicked] = useState<FamilySearchItem | null>(null);

  useEffect(() => {
    if (picked || !query.trim()) {
      setResults([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      searchFamilies(query)
        .then((found) => live && setResults(found.filter((f) => !f.is_draft).slice(0, 6)))
        .catch(() => live && setResults([]));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, picked]);

  return (
    <section aria-labelledby="one-family" className="rounded-3xl border border-border bg-surface p-4 sm:p-6">
      <h2 id="one-family" className="text-[20px] font-semibold">
        Check one family
      </h2>
      <p className="mt-1 text-[16px] text-muted">See what a family can claim under every scheme and grant, and why.</p>

      {picked ? (
        <div className="mt-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <p className="mr-auto min-w-0 text-[18px] font-semibold">
              {picked.primary_contact_name}
              <span className="font-normal text-muted">
                {" "}
                · {picked.family_code}
                {picked.district ? ` · ${picked.district}` : ""}
              </span>
            </p>
            <Link href={`/families?family=${picked.family_id}`} className="inline-flex min-h-11 items-center rounded-full border border-border px-4 text-[15px] hover:bg-surface-2">
              Open family
            </Link>
            <button
              onClick={() => {
                setPicked(null);
                setQuery("");
              }}
              className="min-h-11 px-3 text-[15px] text-accent underline"
            >
              Choose another
            </button>
          </div>
          <FamilyEligibility familyId={picked.family_id} />
        </div>
      ) : (
        <div className="relative mt-4">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a name, family code, district or phone"
            aria-label="Find a family"
            className="min-h-12 w-full rounded-full border border-border bg-bg px-5 text-[17px] outline-none focus:border-accent"
          />
          {results.length > 0 && (
            <ul className="mt-2 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-bg">
              {results.map((f) => (
                <li key={f.family_id}>
                  <button
                    onClick={() => setPicked(f)}
                    className="flex min-h-14 w-full flex-col justify-center px-4 py-2 text-left hover:bg-surface-2"
                  >
                    <span className="text-[17px] font-medium">{f.primary_contact_name}</span>
                    <span className="text-[14px] text-muted">
                      {f.soldier_name ? `w/o ${f.soldier_name} · ` : ""}
                      {f.family_code}
                      {f.district ? ` · ${f.district}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {query.trim() && results.length === 0 && (
            <p className="mt-2 px-2 text-[15px] text-muted">Keep typing… no family found yet.</p>
          )}
        </div>
      )}
    </section>
  );
}

export default function EligibilityPage() {
  const [schemes, setSchemes] = useState<SchemeOverview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    getEligibilityOverview()
      .then((d) => live && setSchemes(d.schemes))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [attempt]);

  return (
    <AppShell>
      <PageHeader
        title="Schemes & grants"
        intro="Every family is checked against every scheme and grant. Each one gives one of four answers, so you can see at a glance who can claim, who needs a detail filled in, and who will be able to later."
      />

      {/* ---------- what the four answers mean ---------- */}
      <ul className="mb-6 flex flex-wrap gap-x-5 gap-y-2 text-[15px]" aria-label="What the answers mean">
        {(["eligible", "needs_data", "eligible_later", "not_eligible"] as const).map((s) => (
          <li key={s} className={`flex items-center gap-2 ${STATUS_LOOK[s].text}`}>
            <span className={`h-2.5 w-5 rounded-full ${STATUS_LOOK[s].bar}`} aria-hidden="true" />
            <StatusIcon status={s} />
            <span className="text-muted">
              <span className="font-medium text-text">
                {{ eligible: "Can claim", needs_data: "Details missing", eligible_later: "Later", not_eligible: "Cannot claim" }[s]}
              </span>{" "}
              — {HINTS[s].toLowerCase()}
            </span>
          </li>
        ))}
      </ul>

      {error && (
        <div className="mb-6 space-y-3">
          <Notice tone="danger" title="The schemes could not be loaded">
            {error}
          </Notice>
          <button onClick={() => setAttempt((n) => n + 1)} className={buttonSecondary}>
            Try again
          </button>
        </div>
      )}

      <div className="space-y-5">
        {!schemes && !error && <div className="h-72 animate-pulse rounded-3xl bg-surface" aria-hidden="true" />}
        {schemes?.map((s) => <SchemeCard key={s.code} scheme={s} />)}

        {schemes && (
          <div className="rounded-3xl border-2 border-dashed border-border px-5 py-6 text-center">
            <p className="text-[17px] font-medium">More schemes and grants will appear here</p>
            <p className="mt-1 text-[15px] text-muted">
              Each new one gets its own card, a column in the families table, and a line in every family&rsquo;s details.
            </p>
          </div>
        )}

        <OneFamily />
      </div>
    </AppShell>
  );
}
