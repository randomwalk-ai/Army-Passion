/**
 * An eligibility answer, shown with an icon and words, never colour alone.
 * The same four answers are used by every scheme.
 */

import type { EligibilityStatus } from "@/lib/api";

export const STATUS_ORDER: EligibilityStatus[] = ["eligible", "needs_data", "eligible_later", "not_eligible"];

export const STATUS_LOOK: Record<
  EligibilityStatus,
  { badge: string; icon: string; bar: string; tile: string; text: string }
> = {
  eligible: {
    badge: "bg-accent-soft text-text",
    icon: "M5 12.5l4.5 4.5L19 7",
    bar: "bg-accent",
    tile: "border-accent/60 bg-accent-soft",
    text: "text-accent",
  },
  needs_data: {
    badge: "bg-surface-2 text-warning",
    icon: "M12 7v6M12 17h.01",
    bar: "bg-warning",
    tile: "border-warning/50 bg-surface",
    text: "text-warning",
  },
  eligible_later: {
    badge: "bg-surface-2 text-text",
    icon: "M12 7v5l3 2",
    bar: "bg-text/45",
    tile: "border-border bg-surface",
    text: "text-text",
  },
  not_eligible: {
    badge: "bg-surface-2 text-muted",
    icon: "M7 7l10 10M17 7L7 17",
    bar: "bg-border",
    tile: "border-border bg-surface",
    text: "text-muted",
  },
};

export function StatusIcon({ status, size = 14 }: { status: EligibilityStatus; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
      {status === "eligible_later" && <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2.2" />}
      <path d={STATUS_LOOK[status].icon} stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function EligibilityBadge({
  status,
  label,
  small = false,
}: {
  status: EligibilityStatus;
  label: string;
  small?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium ${STATUS_LOOK[status].badge} ${
        small ? "px-2.5 py-0.5 text-[13px]" : "px-3 py-1 text-[14px]"
      }`}
    >
      <StatusIcon status={status} size={small ? 12 : 14} />
      {label}
    </span>
  );
}
