"use client";

/**
 * How complete the profiles are, as a bell curve.
 *
 * The curve is a true bell (normal distribution) drawn from the families'
 * average and spread, so it always has the classic shape. Faint bars behind
 * it are the real counts in 5% bands, so he can see how closely the data
 * follows the bell. A picture only: nothing here can be clicked.
 */

import { useEffect, useRef, useState } from "react";
import { getProfileSpread, type ProfileSpread } from "@/lib/api";

const W = 1000;
const H = 260;
const TOP = 16;
const BAND = 5; // bars are 5% wide: 0-4, 5-9 ... 95-100
const BANDS = 20;

const x = (percent: number) => (percent / 100) * W;

/** Families per 5% band if they followed a perfect bell. */
function bell(percent: number, total: number, average: number, spread: number): number {
  const z = (percent - average) / spread;
  return (total * BAND * Math.exp(-0.5 * z * z)) / (spread * Math.sqrt(2 * Math.PI));
}

export default function ProfileCurve() {
  const [data, setData] = useState<ProfileSpread | null>(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<SVGSVGElement>(null);

  useEffect(() => {
    getProfileSpread().then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) return null;
  if (!data) return <div className="h-72 animate-pulse rounded-2xl bg-surface" aria-hidden="true" />;
  if (!data.total) return null;

  const { counts, total, average, spread } = data;
  const bands = Array.from({ length: BANDS }, (_, b) =>
    counts.slice(b * BAND, b === BANDS - 1 ? 101 : (b + 1) * BAND).reduce((a, n) => a + n, 0),
  );
  const hasCurve = spread > 0;
  const peak = hasCurve ? bell(average, total, average, spread) : 0;
  const top = Math.max(...bands, peak) * 1.1 || 1;
  const y = (families: number) => H - (families / top) * (H - TOP);

  const points = hasCurve
    ? Array.from({ length: 201 }, (_, i) => {
        const p = i / 2;
        return `${x(p).toFixed(1)},${y(bell(p, total, average, spread)).toFixed(1)}`;
      })
    : [];
  const line = `M${points.join(" L")}`;

  const low = Math.max(0, Math.round(average - spread));
  const high = Math.min(100, Math.round(average + spread));
  const band = hover === null ? null : Math.min(BANDS - 1, Math.floor(hover / BAND));

  function track(e: React.PointerEvent<SVGSVGElement>) {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return;
    setHover(Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100)));
  }

  return (
    <div className="rounded-2xl border border-border bg-bg p-4 sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-[18px] font-semibold">How complete are the profiles?</h3>
        <p className="text-[15px] text-muted">
          Average <span className="font-semibold text-text">{Math.round(average)}%</span>
        </p>
      </div>
      <div className="relative">
        {band !== null && (
          <div
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-text px-2.5 py-1 text-[14px] text-bg shadow"
            style={{ left: `${Math.min(88, Math.max(12, hover ?? 0))}%` }}
          >
            {bands[band].toLocaleString("en-IN")} {bands[band] === 1 ? "family is" : "families are"}{" "}
            {band * BAND}–{band === BANDS - 1 ? 100 : band * BAND + BAND - 1}% complete
          </div>
        )}
        <svg
          ref={box}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="block h-52 w-full touch-none sm:h-64"
          role="img"
          aria-label={`Bell curve of profile completeness: average ${Math.round(average)}%, most families between ${low}% and ${high}%.`}
          onPointerMove={track}
          onPointerDown={track}
          onPointerLeave={() => setHover(null)}
        >
          {/* the real counts, faint, behind the curve */}
          {bands.map((n, b) => (
            <rect
              key={b}
              x={x(b * BAND) + 3}
              y={y(n)}
              width={x(BAND) - 6}
              height={H - y(n)}
              rx={3}
              className={b === band ? "fill-muted/35" : "fill-muted/15"}
            />
          ))}
          {hasCurve && (
            <>
              <path d={line} fill="none" className="stroke-accent" strokeWidth={3} vectorEffect="non-scaling-stroke" />
            </>
          )}
          <line
            x1={x(average)}
            x2={x(average)}
            y1={0}
            y2={H}
            className="stroke-brass"
            strokeWidth={2}
            strokeDasharray="6 5"
            vectorEffect="non-scaling-stroke"
          />
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} className="stroke-text/30" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          )}
          <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} className="stroke-border" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="mt-1.5 flex justify-between text-[13px] tabular-nums text-muted" aria-hidden="true">
          {[0, 20, 40, 60, 80, 100].map((p) => (
            <span key={p}>{p}%</span>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[14px] text-muted">
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-5 rounded bg-accent" /> Bell curve
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm bg-muted/25" /> Real number of families
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="w-5 border-t-2 border-dashed border-brass" /> Average
        </span>
      </div>
    </div>
  );
}
