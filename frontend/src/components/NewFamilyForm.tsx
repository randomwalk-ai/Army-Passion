"use client";

import { useState } from "react";
import type { NewFamilyInput } from "@/lib/api";

type Props = {
  /** What the recording appeared to say. Marked as heard, never assumed. */
  heard: Record<string, string>;
  onSave: (details: NewFamilyInput) => void;
  onCancel: () => void;
  saving: boolean;
};

const FIELDS: { key: keyof NewFamilyInput; label: string; hint?: string }[] = [
  { key: "widow_name", label: "Widow's name" },
  { key: "soldier_name", label: "Soldier's name" },
  { key: "rank", label: "Rank" },
  { key: "unit", label: "Regiment or unit" },
  { key: "service_number", label: "Service number" },
  { key: "date_of_death", label: "Date of death", hint: "DD-MM-YYYY" },
  { key: "cause_of_death", label: "Cause of death" },
  { key: "district", label: "District" },
  { key: "state", label: "State" },
  { key: "phone", label: "Phone number", hint: "+91 or 10 digits" },
];

export default function NewFamilyForm({ heard, onSave, onCancel, saving }: Props) {
  const [values, setValues] = useState<NewFamilyInput>(() => ({ ...heard }));

  const hasName = Boolean(values.widow_name?.trim() || values.soldier_name?.trim());

  return (
    <div>
      <h3 className="text-[15px] font-semibold">New family</h3>
      <p className="mt-1 text-[15px] leading-relaxed text-muted">
        I filled in what I heard in the recording. Check it, add anything you know,
        and leave the rest blank — anything missing is added to the needs-attention list.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {FIELDS.map((field) => {
          const wasHeard = Boolean(heard[field.key]);
          return (
            <label key={field.key} className="block">
              <span className="block text-sm font-medium">
                {field.label}
                {wasHeard && (
                  <span className="ml-2 text-xs font-normal text-accent">heard</span>
                )}
              </span>
              <input
                value={values[field.key] ?? ""}
                placeholder={field.hint ?? ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2
                  text-[15px] outline-none focus:border-accent"
              />
            </label>
          );
        })}
      </div>

      {!hasName && (
        <p className="mt-3 text-[15px] text-danger">
          I need at least the widow&rsquo;s name or the soldier&rsquo;s name.
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          onClick={() => onSave(values)}
          disabled={!hasName || saving}
          className="rounded-full bg-accent px-5 py-2.5 text-[15px] font-medium text-accent-fg
            disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
        >
          {saving ? "Saving..." : "Save family"}
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className="rounded-full border border-border px-5 py-2.5 text-[15px] hover:bg-surface-2"
        >
          Back
        </button>
      </div>
    </div>
  );
}
