"use client";

/** The frame every page sits in: the menu on the left, the page on the right. */

import { useEffect, useState } from "react";
import { StarMark, Tricolour } from "@/components/Decor";
import Sidebar from "@/components/Sidebar";

/**
 * Two ways of showing the tricolour behind every page, kept side by side
 * until one is chosen:
 * 1 = a saffron glow top-right and a green glow bottom-left, with a thin
 *     stripe along the top;
 * 2 = the whole page washed in the flag's order (saffron top, white middle,
 *     green bottom), with a thicker stripe along the top;
 * 3 = a diagonal wash (saffron top-left to green bottom-right), with the
 *     tricolour running down beside the menu and a thin stripe along the top;
 * 4 = no wash: the Ashoka Chakra, large and faint, turning very slowly in
 *     the bottom-right, with a thicker stripe along the top;
 * 5 = the flag waving: three soft wavy bands (saffron, white, green) across
 *     the top of the page, drifting slowly sideways;
 * 6 = letterhead: a plain, calm page with a still tricolour stripe along the
 *     top and the bottom of the screen. Nothing moves;
 * 7 = 2 and 5 together: the flag-order wash with softer waves across the top,
 *     and a thicker stripe along the top;
 * 8 = 2 and 4 together: the flag-order wash with the faint Ashoka Chakra
 *     turning in the bottom-right, and a thicker stripe along the top.
 */
const FLAG_LOOK: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 = 2;

/** One wave band, twice as wide as the page so it can drift and repeat. */
const WAVE = (y: number) =>
  `M0 ${y} C150 ${y - 28} 350 ${y + 28} 500 ${y} S850 ${y - 28} 1000 ${y} ` +
  `S1350 ${y + 28} 1500 ${y} S1850 ${y - 28} 2000 ${y} V${y + 34} ` +
  `C1850 ${y + 62} 1650 ${y + 6} 1500 ${y + 34} S1150 ${y + 62} 1000 ${y + 34} ` +
  `S650 ${y + 6} 500 ${y + 34} S150 ${y + 62} 0 ${y + 34} Z`;

function FlagWave({ soft = false }: { soft?: boolean }) {
  return (
    <svg
      viewBox="0 0 1000 150"
      preserveAspectRatio="none"
      className={`flag-wave absolute inset-x-0 top-0 h-44 w-full ${soft ? "soft" : ""}`}
      aria-hidden="true"
    >
      <g className="drift">
        <path d={WAVE(20)} fill="var(--saffron)" />
        <path d={WAVE(54)} fill="#ffffff" />
        <path d={WAVE(88)} fill="var(--india-green)" />
      </g>
    </svg>
  );
}

/** The 24-spoke wheel from the flag, drawn as lines so it stays crisp at any size. */
function AshokaChakra({ className = "" }: { className?: string }) {
  const spokes = Array.from({ length: 24 }, (_, i) => (i * 360) / 24);
  return (
    <svg viewBox="-50 -50 100 100" className={className} aria-hidden="true">
      <circle r="46" fill="none" stroke="currentColor" strokeWidth="3" />
      <circle r="7" fill="currentColor" />
      {spokes.map((angle) => (
        <g key={angle} transform={`rotate(${angle})`}>
          <path d="M0 -7 L1.6 -26 L0 -44 L-1.6 -26 Z" fill="currentColor" />
          <circle cy="-46" r="1.6" fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}

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

      <div className="relative isolate flex min-w-0 flex-1 flex-col">
        {/* The tricolour, far behind the page (see FLAG_LOOK). */}
        {FLAG_LOOK === 1 ? (
          <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
            <div className="ambient-glow saffron -right-32 -top-40 h-[38rem] w-[38rem]" />
            <div className="ambient-glow green -bottom-48 -left-32 h-[40rem] w-[40rem]" />
          </div>
        ) : FLAG_LOOK === 2 ? (
          <div className="flag-wash pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />
        ) : FLAG_LOOK === 8 ? (
          <div className="flag-wash pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
            <AshokaChakra className="chakra-watermark absolute -bottom-40 -right-40 h-[42rem] w-[42rem]" />
          </div>
        ) : FLAG_LOOK === 7 ? (
          <div className="flag-wash pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
            <FlagWave soft />
          </div>
        ) : FLAG_LOOK === 6 ? (
          <Tricolour bottom className="still thick z-10 hidden md:block" />
        ) : FLAG_LOOK === 5 ? (
          <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
            <FlagWave />
          </div>
        ) : FLAG_LOOK === 4 ? (
          <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
            <AshokaChakra className="chakra-watermark absolute -bottom-40 -right-40 h-[42rem] w-[42rem]" />
          </div>
        ) : (
          <>
            <div className="flag-diagonal pointer-events-none absolute inset-0 -z-10" aria-hidden="true" />
            <div className="tricolour-down pointer-events-none absolute inset-y-0 left-0 z-10 hidden md:block" aria-hidden="true" />
          </>
        )}
        {/* The tricolour along the top of every page (a phone has it in its header). */}
        <Tricolour
          className={`z-10 hidden md:block ${FLAG_LOOK === 2 || FLAG_LOOK === 4 || FLAG_LOOK === 6 || FLAG_LOOK === 7 || FLAG_LOOK === 8 ? "thick" : ""} ${
            FLAG_LOOK === 6 ? "still" : ""
          }`}
        />

        {/* On a phone the menu hides behind this button. */}
        <header className="pt-safe olive-panel relative shrink-0 border-b border-border md:hidden">
          <Tricolour />
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
            <span className="flex items-center gap-2 text-[17px] font-semibold">
              <span className="text-accent"><StarMark size={18} /></span>
              Army Passion
            </span>
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
