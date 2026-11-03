/**
 * Who is using the screen. There is no login yet, so this is a placeholder,
 * read from frontend/.env.local (see frontend/.env.example). Never hard-code
 * a real person's name in the screens; replace this with the logged-in user
 * once login exists.
 */

export const CURRENT_USER = {
  name: process.env.NEXT_PUBLIC_USER_NAME || "Demo User",
  role: process.env.NEXT_PUBLIC_USER_ROLE || "Administrator",
};

/** "Demo User" -> "DU", for the round badge in the menu. */
export function initials(name: string = CURRENT_USER.name): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}
