"use client";

/** One on/off switch: Dark mode. */

import { useEffect, useState } from "react";
import { currentTheme, setTheme } from "@/lib/theme";

export default function ThemeSwitch() {
  // Unknown until the browser tells us; avoids drawing the switch the wrong way round.
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(currentTheme() === "dark");
    // While he has not chosen, follow the computer if it changes (e.g. at sunset).
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => {
      if (!document.documentElement.hasAttribute("data-theme")) setDark(media.matches);
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);

  function toggle() {
    const next = !(dark ?? currentTheme() === "dark");
    setTheme(next ? "dark" : "light");
    setDark(next);
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark ?? false}
      onClick={toggle}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[16px] text-muted
        transition hover:bg-surface-2 hover:text-text"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        {dark ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        ) : (
          <path
            d="M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66l1.42-1.42M4.92 19.08l1.42-1.42m0-11.32L4.92 4.92m14.16 14.16l-1.42-1.42M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        )}
      </svg>
      <span className="flex-1">Dark mode</span>
      {/* The switch itself */}
      <span
        aria-hidden="true"
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${dark ? "bg-accent" : "bg-border"}`}
      >
        <span
          className={`absolute top-1 h-5 w-5 rounded-full bg-bg shadow transition-all ${dark ? "left-6" : "left-1"}`}
        />
      </span>
    </button>
  );
}
