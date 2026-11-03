"use client";

/** The left column: start something new, and look back at what was done. */

type Props = {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
};

// Placeholder history. Real sessions get stored once the backend is wired up.
const RECENT = [
  "Imported widows_sheet_oct.xlsx",
  "Voice note — Kamlesh Devi, Rohtak",
  "Voice note — new family, 9 Jat",
  "Imported pension_update_sep.xlsx",
];

export default function Sidebar({ open, onClose, onNewChat }: Props) {
  return (
    <>
      {/* On a phone the sidebar slides over the page; this dims what is behind. */}
      {open && (
        <button
          aria-label="Close menu"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-border bg-surface
          transition-transform duration-200 md:static md:translate-x-0
          ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <span className="text-lg font-semibold tracking-tight">Army Passion</span>
          <button
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-lg p-1.5 text-muted hover:bg-surface-2 md:hidden"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M6 6l12 12M18 6L6 18"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="px-4">
          <button
            onClick={onNewChat}
            className="flex w-full items-center gap-2.5 rounded-full border border-border bg-bg px-4 py-3
              text-left text-base font-medium hover:bg-surface-2"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 5v14M5 12h14"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            New
          </button>
        </div>

        <nav className="mt-7 flex-1 overflow-y-auto px-4">
          <h2 className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Recent
          </h2>
          <ul className="space-y-0.5">
            {RECENT.map((item) => (
              <li key={item}>
                <button
                  className="w-full truncate rounded-lg px-3 py-2.5 text-left text-[15px]
                    text-muted hover:bg-surface-2 hover:text-text"
                  title={item}
                >
                  {item}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <div className="border-t border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full
                bg-accent text-sm font-semibold text-accent-fg"
              aria-hidden="true"
            >
              VR
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">Col. Vikram Rathore</p>
              <p className="truncate text-xs text-muted">Colonel (Retd)</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
