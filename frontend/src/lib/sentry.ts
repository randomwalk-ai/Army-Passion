/** Error reporting to sentry.io, shared by the browser and the server.
 *
 * Switched on only when NEXT_PUBLIC_SENTRY_DSN is set (on Render). It is
 * fixed when the screens are built, so changing it needs a redeploy.
 *
 * PRIVACY: an error report must never carry a family's details. No user, no
 * IP address, no cookies, no form values, no screen recording (replay), and
 * no query strings (a search like ?q=Paramjit Kaur). What is left: the error,
 * where in the code it happened, which page, and when.
 */

import type { ErrorEvent, Breadcrumb } from "@sentry/nextjs";

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN ?? "";

const withoutQuery = (url: string) => url.split("?")[0];

/** Last check before an event leaves: remove anything personal. */
export function scrub(event: ErrorEvent): ErrorEvent {
  delete event.user;
  if (event.request) {
    delete event.request.data;
    delete event.request.cookies;
    delete event.request.query_string;
    delete event.request.headers;
    if (event.request.url) event.request.url = withoutQuery(event.request.url);
  }
  return event;
}

/** Keep the useful trail of what happened, minus anything typed or searched. */
export function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb | null {
  // Typing in a box: never record it.
  if (crumb.category === "ui.input") return null;
  if (crumb.data && typeof crumb.data.url === "string") {
    crumb.data.url = withoutQuery(crumb.data.url);
  }
  if (crumb.data && typeof crumb.data.to === "string") crumb.data.to = withoutQuery(crumb.data.to);
  if (crumb.data && typeof crumb.data.from === "string") crumb.data.from = withoutQuery(crumb.data.from);
  return crumb;
}

/** The same settings everywhere Sentry starts. */
export const sentryOptions = {
  dsn: SENTRY_DSN,
  enabled: SENTRY_DSN !== "",
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "production",
  sendDefaultPii: false,
  // Errors only: no performance tracing and no screen recording.
  tracesSampleRate: 0,
  beforeSend: scrub,
  beforeBreadcrumb: scrubBreadcrumb,
};
