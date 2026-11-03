/**
 * Light or dark.
 *
 * The colours themselves live in globals.css. Until he presses the switch the
 * page follows the computer's setting; once he does, his choice is set as
 * `data-theme="light" | "dark"` on <html> and remembered in this browser.
 */

export type Theme = "light" | "dark";

const KEY = "army-passion-theme";

/** Inlined in <head>; must stay plain, self-contained JavaScript. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;

/** What is showing right now: his choice, or else the computer's setting. */
export function currentTheme(): Theme {
  const chosen = document.documentElement.getAttribute("data-theme");
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // private window or blocked storage: the switch still works for this visit
  }
}
