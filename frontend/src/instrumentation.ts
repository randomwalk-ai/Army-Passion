// Runs on the server when it starts: reports errors from building pages.
// Does nothing unless NEXT_PUBLIC_SENTRY_DSN was set when the app was built.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentry";

export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init(sentryOptions);
  }
}

// Called by Next.js when a page or route fails on the server.
export const onRequestError = Sentry.captureRequestError;
