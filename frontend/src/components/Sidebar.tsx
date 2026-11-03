"use client";

/** The left column: where to go, and (on the assistant) what was done. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeSwitch from "@/components/ThemeSwitch";
import { CURRENT_USER, initials } from "@/lib/currentUser";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Only the assistant has chats to start and look back on. */
  onNewChat?: () => void;
};

// Placeholder history. Real sessions get stored once the backend is wired up.
const RECENT = [
  "Imported widows_sheet_oct.xlsx",
  "Voice note — Kamlesh Devi, Rohtak",
  "Voice note — new family, 9 Jat",
  "Imported pension_update_sep.xlsx",
];

type NavItem = { href: string; label: string; icon: string; soon?: boolean };

export const NAV: NavItem[] = [
  { href: "/", label: "Home", icon: "M4 11l8-7 8 7v8.5a.5.5 0 0 1-.5.5H15v-6H9v6H4.5a.5.5 0 0 1-.5-.5V11z" },
  { href: "/families", label: "All families", icon: "M4 5h16v14H4zM4 10h16M4 14.5h16M10 10v9" },
  { href: "/upload", label: "Upload a sheet", icon: "M12 16V4m0 0L7 9m5-5l5 5M5 20h14" },
  { href: "/families/new", label: "Add a family", icon: "M12 5v14M5 12h14" },
  { href: "/cea", label: "CEA claims", icon: "M4 8l8-4 8 4-8 4-8-4zm3 2v5c0 1.5 2.5 3 5 3s5-1.5 5-3v-5" },
  { href: "/voice", label: "Voice notes", icon: "M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v3", soon: true },
  { href: "/assistant", label: "Assistant", icon: "M5 5h14v10H9l-4 4V5z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d={d} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Sidebar({ open, onClose, onNewChat }: Props) {
  const pathname = usePathname();
  // The closest match wins, so "Add a family" and "All families" are not both lit.
  const matches = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  const current = NAV.filter((item) => matches(item.href)).sort((a, b) => b.href.length - a.href.length)[0];
  const isActive = (href: string) => current?.href === href;

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
        className={`pt-safe fixed inset-y-0 left-0 z-40 flex w-[min(18rem,85vw)] flex-col border-r border-border bg-surface md:w-72
          transition-transform duration-200 md:static md:translate-x-0
          ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/" onClick={onClose} className="flex items-center gap-2.5">
            <span
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-accent-fg"
              aria-hidden="true"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9L12 3z"
                  fill="currentColor"
                />
              </svg>
            </span>
            <span className="text-lg font-semibold tracking-tight">Army Passion</span>
          </Link>
          <button
            onClick={onClose}
            aria-label="Close menu"
            className="-mr-2 flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface-2 md:hidden"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <nav className="px-3" aria-label="Main">
          <ul className="space-y-1">
            {NAV.map((item) =>
              item.soon ? (
                <li key={item.href}>
                  <span
                    aria-disabled="true"
                    className="flex items-center gap-3 rounded-xl px-3 py-3 text-[16px] text-muted"
                  >
                    <Icon d={item.icon} />
                    <span className="flex-1">{item.label}</span>
                    <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-medium">
                      Soon
                    </span>
                  </span>
                </li>
              ) : (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onClose}
                    aria-current={isActive(item.href) ? "page" : undefined}
                    className={`flex items-center gap-3 rounded-xl px-3 py-3 text-[16px] transition-colors
                      ${
                        isActive(item.href)
                          ? "bg-accent-soft font-semibold text-text"
                          : "text-muted hover:bg-surface-2 hover:text-text"
                      }`}
                  >
                    <span className={isActive(item.href) ? "text-accent" : ""}>
                      <Icon d={item.icon} />
                    </span>
                    {item.label}
                  </Link>
                </li>
              ),
            )}
          </ul>
        </nav>

        <div className="mt-6 flex-1 overflow-y-auto px-4">
          {onNewChat && (
            <>
              <button
                onClick={onNewChat}
                className="flex w-full items-center gap-2.5 rounded-full border border-border bg-bg px-4 py-3
                  text-left text-base font-medium hover:bg-surface-2"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                New chat
              </button>
              <h2 className="px-3 pb-2 pt-6 text-xs font-semibold uppercase tracking-wide text-muted">
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
            </>
          )}
        </div>

        <div className="pb-safe border-t border-border px-5 pt-3">
          <div className="-mx-2 mb-3">
            <ThemeSwitch />
          </div>
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full
                bg-accent text-sm font-semibold text-accent-fg"
              aria-hidden="true"
            >
              {initials()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{CURRENT_USER.name}</p>
              <p className="truncate text-xs text-muted">{CURRENT_USER.role}</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
