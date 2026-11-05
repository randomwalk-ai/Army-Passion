import type { Config } from "tailwindcss";

/**
 * A colour from globals.css that also works with Tailwind's "/60" opacity
 * classes (e.g. ring-accent/15). A plain token("accent") silently drops them.
 */
const token = (name: string) =>
  `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`;

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        "surface-2": token("surface-2"),
        border: token("border"),
        text: token("text"),
        muted: token("text-muted"),
        accent: token("accent"),
        "accent-soft": token("accent-soft"),
        "accent-fg": token("accent-fg"),
        brass: token("brass"),
        success: token("success"),
        danger: token("danger"),
        warning: token("warning"),
      },
    },
  },
  plugins: [],
} satisfies Config;
