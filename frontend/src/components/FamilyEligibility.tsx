"use client";

/** What one family can claim, scheme by scheme, with the reasons. */

import Link from "next/link";
import { useEffect, useState } from "react";
import EligibilityBadge, { STATUS_LOOK } from "@/components/EligibilityBadge";
import { Notice, errorText } from "@/components/ui";
import { getFamilyEligibility, rupees, type FamilyScheme } from "@/lib/api";

export default function FamilyEligibility({ familyId }: { familyId: number }) {
  const [schemes, setSchemes] = useState<FamilyScheme[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setSchemes(null);
    setError(null);
    getFamilyEligibility(familyId)
      .then((s) => live && setSchemes(s))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [familyId]);

  if (error) {
    return (
      <Notice tone="danger" title="The schemes could not be checked">
        {error}
      </Notice>
    );
  }
  if (!schemes) {
    return (
      <p className="py-3 text-[16px] text-muted" role="status">
        Checking every scheme and grant…
      </p>
    );
  }

  return (
    <ul className="space-y-2.5">
      {schemes.map((s) => {
        const act = s.status === "eligible" || s.status === "needs_data";
        return (
          <li key={s.code} className={`rounded-2xl border p-3.5 sm:p-4 ${STATUS_LOOK[s.status].tile}`}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <p className="mr-auto text-[17px] font-semibold">{s.name}</p>
              <EligibilityBadge status={s.status} label={s.label} />
            </div>
            <p className="mt-1 text-[14px] text-muted">{s.period}</p>
            <p className="mt-2 text-[16px] leading-snug">{s.headline}</p>
            {s.amount > 0 && (
              <p className="mt-1 text-[16px]">
                Worth about <span className="font-semibold tabular-nums">{rupees(s.amount)}</span>
              </p>
            )}
            {s.reasons.length > 1 && (
              <details className="group mt-2">
                <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-1 text-[15px] text-accent [&::-webkit-details-marker]:hidden">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="transition group-open:rotate-90" aria-hidden="true">
                    <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Why?
                </summary>
                <ul className="mt-1 space-y-1 text-[15px] text-muted">
                  {s.reasons.map((r) => (
                    <li key={r} className="rounded-lg bg-bg px-3 py-2">
                      {r}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {s.href && act && (
              <Link
                href={s.href}
                className={`mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-full px-4 text-[15px] font-semibold ${
                  s.status === "eligible" ? "bg-accent text-accent-fg" : "border border-border bg-bg"
                }`}
              >
                {s.status === "eligible" ? "Fill the claim" : "Fill in the missing details"}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Link>
            )}
          </li>
        );
      })}
    </ul>
  );
}
