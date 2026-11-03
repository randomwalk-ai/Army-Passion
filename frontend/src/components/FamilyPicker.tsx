"use client";

import { useEffect, useState } from "react";
import { searchFamilies, type FamilySearchItem } from "@/lib/api";

type Props = {
  onPick: (family: FamilySearchItem) => void;
  /** Leave out where a new family makes no sense, e.g. attaching a document. */
  onNewFamily?: () => void;
  title?: string;
};

/** Find the family this is about — or, if allowed, say it is a new one. */
export default function FamilyPicker({
  onPick,
  onNewFamily,
  title = "Who is this about?",
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FamilySearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Wait until he stops typing before asking the server.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      searchFamilies(query)
        .then((found) => !cancelled && setResults(found))
        .catch((e: unknown) =>
          setError(e instanceof Error ? e.message : "Could not search."),
        )
        .finally(() => !cancelled && setLoading(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div>
      <h3 className="text-[15px] font-semibold">{title}</h3>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by name, family code, district or phone"
        className="mt-2 w-full rounded-lg border border-border bg-bg px-3 py-2.5
          text-[15px] outline-none focus:border-accent"
      />

      {onNewFamily && (
        <button
          onClick={onNewFamily}
          className="mt-2 flex w-full items-center gap-2 rounded-lg border border-dashed
            border-accent px-3 py-2.5 text-left text-[15px] font-medium text-accent
            hover:bg-accent-soft"
        >
          <span aria-hidden="true">+</span> This is a new family
        </button>
      )}

      {error && <p className="mt-2 text-[15px] text-danger">{error}</p>}

      <ul className="mt-2 max-h-72 overflow-y-auto">
        {results.map((family) => (
          <li key={family.family_id}>
            <button
              onClick={() => onPick(family)}
              className="w-full border-t border-border px-1 py-2.5 text-left hover:bg-surface-2"
            >
              <span className="block text-[15px] font-medium">
                {family.primary_contact_name}
                {family.is_draft && (
                  <span className="ml-2 rounded bg-warning/20 px-1.5 py-0.5 text-xs text-warning">
                    draft
                  </span>
                )}
              </span>
              <span className="block text-xs text-muted">
                {family.family_code}
                {family.soldier_name && ` · ${family.soldier_name}`}
                {family.district && ` · ${family.district}`}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {!loading && results.length === 0 && (
        <p className="mt-2 text-[15px] text-muted">
          No family found.
          {onNewFamily &&
            " If they are not on record yet, use “This is a new family” above."}
        </p>
      )}
    </div>
  );
}
