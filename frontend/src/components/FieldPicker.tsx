"use client";

import { useMemo, useRef, useState } from "react";
import { EXTRA_PREFIX, IGNORE, type TargetField } from "@/lib/api";

type Props = {
  value: string;
  options: TargetField[];
  /** The sheet heading, used as the suggested name for a new field. */
  heading: string;
  onChange: (value: string) => void;
  /** Create a new extra field. Returns its mapping key, e.g. "extra:panchayat". */
  onCreateField: (label: string) => Promise<string>;
  invalid?: boolean;
  /** A new field proposed for this column but not created yet. */
  proposedLabel?: string | null;
};

const SKIP = "";

/** Type to search our fields, or add a new one when nothing fits. */
export default function FieldPicker({
  value,
  options,
  heading,
  onChange,
  onCreateField,
  invalid,
  proposedLabel,
}: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selected = options.find((o) => o.key === value);
  let selectedLabel = "";
  if (selected) {
    selectedLabel = selected.label;
  } else if (value === IGNORE) {
    selectedLabel = "Do not import this column";
  } else if (proposedLabel) {
    // Nothing chosen, but a new field is proposed. Say so, rather than
    // showing an empty box that looks like nothing was decided.
    selectedLabel = `New field: ${proposedLabel}`;
  }

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return options;
    return options.filter(
      (o) =>
        o.label.toLowerCase().includes(term) ||
        o.group.toLowerCase().includes(term),
    );
  }, [options, query]);

  // Offer to add a field only when the typed name matches nothing we have.
  const typed = query.trim();
  const canCreate =
    typed.length >= 2 &&
    !options.some((o) => o.label.toLowerCase() === typed.toLowerCase());

  function choose(key: string) {
    onChange(key);
    setQuery("");
    setOpen(false);
    setError(null);
  }

  async function create() {
    setCreating(true);
    setError(null);
    try {
      choose(await onCreateField(typed));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add that field.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="relative">
      <input
        value={open ? query : selectedLabel}
        placeholder={selectedLabel ? "" : "Type to find a field..."}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onBlur={() => {
          // Let a click on the list register before closing it.
          blurTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        onChange={(e) => setQuery(e.target.value)}
        className={`w-full rounded-lg border bg-bg px-3 py-2 text-[15px] outline-none
          focus:border-accent ${invalid ? "border-danger" : "border-border"}`}
      />

      {open && (
        <div
          onMouseDown={() => {
            if (blurTimer.current) clearTimeout(blurTimer.current);
          }}
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg
            border border-border bg-bg shadow-lg"
        >
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => choose(SKIP)}
            className="block w-full px-3 py-2 text-left text-[15px] text-muted hover:bg-surface-2"
          >
            -- not sure, skip this column --
          </button>
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => choose(IGNORE)}
            className="block w-full px-3 py-2 text-left text-[15px] text-muted hover:bg-surface-2"
          >
            Do not import this column
          </button>

          {matches.map((option) => (
            <button
              key={option.key}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(option.key)}
              className="block w-full px-3 py-2 text-left text-[15px] hover:bg-surface-2"
            >
              {option.label}
              {option.required && (
                <span className="ml-1 text-xs text-muted">(needed)</span>
              )}
              <span className="ml-2 text-xs text-muted">
                {option.key.startsWith(EXTRA_PREFIX) ? "added before" : option.group}
              </span>
            </button>
          ))}

          {matches.length === 0 && !canCreate && (
            <p className="px-3 py-2 text-[15px] text-muted">Nothing matches.</p>
          )}

          {canCreate && (
            <button
              onMouseDown={(e) => e.preventDefault()}
              onClick={create}
              disabled={creating}
              className="block w-full border-t border-border px-3 py-2.5 text-left
                text-[15px] font-medium text-accent hover:bg-accent-soft"
            >
              {creating ? "Adding..." : `+ Store as a new field "${typed}"`}
            </button>
          )}

          {typed.length === 0 && (
            <button
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setQuery(heading);
              }}
              className="block w-full border-t border-border px-3 py-2 text-left
                text-xs text-muted hover:bg-surface-2"
            >
              or add a new field called &ldquo;{heading}&rdquo;
            </button>
          )}
        </div>
      )}

      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
