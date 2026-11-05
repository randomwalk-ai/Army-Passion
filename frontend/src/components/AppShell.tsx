"use client";

/** The frame every page sits in: the menu on the left, the page on the right. */

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";

export default function AppShell({
  children,
  wide = false,
}: {
  children: React.ReactNode;
  /** For the families table, which needs the whole width of a big screen. */
  wide?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  // The Back key / Escape closes the menu on a phone.
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);

  return (
    <div className="app-height flex overflow-hidden bg-bg">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* On a phone the menu hides behind this button. */}
        <header className="pt-safe olive-panel shrink-0 border-b border-border md:hidden">
          <div className="flex h-14 items-center gap-1 px-2">
            <button
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              aria-expanded={menuOpen}
              className="flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-text"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
            <span className="text-[17px] font-semibold">Army Passion</span>
          </div>
        </header>

        {/* scroll-padding keeps a focused box clear of the sticky Save bars. */}
        <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain scroll-pb-44">
          <div className={`pb-safe mx-auto w-full ${wide ? "max-w-[100rem]" : "max-w-5xl"} px-4 pt-5 sm:px-8 sm:pb-16 sm:pt-10`}>{children}</div>
        </main>
      </div>
    </div>
  );
}
