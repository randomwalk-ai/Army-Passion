// Runs in the browser before the app starts: reports errors to Sentry.
// Does nothing unless NEXT_PUBLIC_SENTRY_DSN was set when the app was built.
import * as Sentry from "@sentry/nextjs";
import { sentryOptions } from "@/lib/sentry";

Sentry.init({
  ...sentryOptions,
  // No screen recording, ever: it would capture families' details on screen.
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0,
});

// Lets Sentry note which page the colonel moved to before an error.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
