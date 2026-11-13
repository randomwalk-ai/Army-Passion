import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { THEME_SCRIPT } from "@/lib/theme";

// A clear, modern font for the quieter working pages (see .font-calm).
// Next downloads it at build time and serves it itself: no call to Google from the browser.
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-calm", preload: false });

export const metadata: Metadata = {
  title: "Army Passion",
  description:
    "Support for the families of soldiers who have died — schemes, applications and contact in one place.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Lets the page use the full screen on phones with a notch; the frame pads
  // itself clear of it (see .pt-safe / .pb-safe in globals.css).
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#2f3a22" },
    { media: "(prefers-color-scheme: dark)", color: "#171b13" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // The theme script sets data-theme before React loads, so the server's
    // HTML and the browser's differ on that one attribute. That is expected.
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        {/* Runs before the page is painted, so a dark-mode user never sees a white flash. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
