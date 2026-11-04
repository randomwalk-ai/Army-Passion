"use client";

/** Shown when a screen crashes completely; the error goes to Sentry. */

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: "48px 24px", maxWidth: 560 }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>Something went wrong</h1>
        <p style={{ fontSize: 17, lineHeight: 1.6, color: "#555" }}>
          This screen could not be shown. The problem has been noted. Please try again.
        </p>
        <button
          type="button"
          onClick={reset}
          style={{ fontSize: 17, padding: "12px 20px", borderRadius: 12, border: "1px solid #ccc", cursor: "pointer" }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
