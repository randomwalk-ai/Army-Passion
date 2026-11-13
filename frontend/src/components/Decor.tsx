"use client";

/**
 * Small decorative pieces that give the screens their Army feel:
 * the tricolour stripe, survey-map contour lines, the brass star and
 * numbers that count up. All are hidden from screen readers, and all motion
 * stops when the computer is set to "reduce motion" (see globals.css).
 *
 * We use the colours of the flag, never the flag itself or the national
 * emblem: both have legal rules about how they may be shown.
 */

import { useEffect, useState } from "react";

/**
 * Saffron, white and green in a thin band along the top edge of its parent
 * (which must be positioned), with a slow light sweeping along it.
 */
export function Tricolour({ className = "", bottom = false }: { className?: string; bottom?: boolean }) {
  return (
    <div
      className={`tricolour absolute inset-x-0 ${bottom ? "bottom-0" : "top-0"} ${className}`}
      aria-hidden="true"
    />
  );
}

/** Three short dashes above a page title. The white one has an outline so it shows on light pages. */
export function TricolourRule({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-1 ${className}`} aria-hidden="true">
      <span className="h-1 w-5 rounded-full bg-saffron" />
      <span className="h-1 w-5 rounded-full bg-white ring-1 ring-inset ring-border" />
      <span className="h-1 w-5 rounded-full bg-india-green" />
    </span>
  );
}

/* ---------- survey-map contour lines ---------- */

/**
 * Rings of "height lines" around a few hilltops, like an Army map sheet.
 * Worked out once, with fixed numbers, so the server and the browser draw
 * exactly the same picture.
 */
function ring(cx: number, cy: number, r: number, seed: number): string {
  const steps = 72;
  let d = "";
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const wobble = 1 + 0.13 * Math.sin(3 * t + seed) + 0.07 * Math.sin(5 * t + seed * 1.7);
    const x = cx + Math.cos(t) * r * wobble * 1.25;
    const y = cy + Math.sin(t) * r * wobble;
    d += `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  return d + "Z";
}

const HILLS = [
  { cx: 120, cy: 140, rings: 9, seed: 0.4 },
  { cx: 520, cy: 420, rings: 11, seed: 2.1 },
  { cx: 860, cy: 120, rings: 7, seed: 4.3 },
];

const CONTOUR_PATH = HILLS.flatMap((h) =>
  Array.from({ length: h.rings }, (_, k) => ring(h.cx, h.cy, 18 + k * 26, h.seed + k * 0.35)),
).join("");

/** Fills its (positioned) parent with faint contour lines that drift very slowly. */
export function Contours({ className = "" }: { className?: string }) {
  return (
    <div className={`pointer-events-none absolute inset-0 -z-10 overflow-hidden ${className}`} aria-hidden="true">
      <svg
        className="contour-drift absolute -inset-[15%] h-[130%] w-[130%]"
        viewBox="0 0 1000 600"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
      >
        <path d={CONTOUR_PATH} stroke="currentColor" strokeWidth="1.2" />
      </svg>
    </div>
  );
}

/** The five-pointed star used as the app's mark. */
export function StarMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9L12 3z"
        fill="currentColor"
      />
    </svg>
  );
}

/* ---------- numbers that count up ---------- */

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts from 0 up to `target` in under a second; shows `target` straight away if motion is off. */
export function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion() || target === 0) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(target * eased));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return value;
}
