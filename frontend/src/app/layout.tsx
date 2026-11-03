import type { Metadata, Viewport } from "next";
import "./globals.css";
import { THEME_SCRIPT } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Army Passion",
  description:
    "Support for the families of soldiers who have died — schemes, applications and contact in one place.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#141413" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // The theme script sets data-theme before React loads, so the server's
    // HTML and the browser's differ on that one attribute. That is expected.
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Runs before the page is painted, so a dark-mode user never sees a white flash. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
