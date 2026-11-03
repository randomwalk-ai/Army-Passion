/** A CEA verdict, shown with an icon and words, never colour alone. */

import type { CeaStatus } from "@/lib/api";

export default function CeaStatusBadge({ status, label }: { status: CeaStatus; label: string }) {
  const style = {
    eligible: "bg-accent-soft text-text",
    needs_data: "bg-surface-2 text-warning",
    eligible_later: "bg-surface-2 text-text",
    not_eligible: "bg-surface-2 text-muted",
  }[status];
  const icon = {
    eligible: "M5 12.5l4.5 4.5L19 7",
    needs_data: "M12 7v6M12 17h.01",
    eligible_later: "M12 7v5l3 2",
    not_eligible: "M7 7l10 10M17 7L7 17",
  }[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[14px] font-medium ${style}`}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d={icon} stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {label}
    </span>
  );
}
