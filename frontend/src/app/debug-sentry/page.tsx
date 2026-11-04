"use client";

/** A hidden page (not in the menu) to check that errors reach the Sentry
 *  dashboard. Each button breaks something on purpose. */

import * as Sentry from "@sentry/nextjs";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { Card, Notice, PageHeader, buttonSecondary } from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { SENTRY_DSN } from "@/lib/sentry";

type Result = { tone: "success" | "warning" | "danger"; title: string; body: string };

export default function DebugSentry() {
  const [backendOn, setBackendOn] = useState<boolean | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const frontendOn = SENTRY_DSN !== "";

  useEffect(() => {
    fetch(`${API_BASE}/api/debug/sentry`)
      .then((r) => r.json())
      .then((body) => setBackendOn(Boolean(body.enabled)))
      .catch(() => setBackendOn(false));
  }, []);

  async function breakBackend() {
    try {
      const response = await fetch(`${API_BASE}/api/debug/sentry`, { method: "POST" });
      if (response.status >= 500) {
        setResult({
          tone: "success",
          title: "Backend test error sent",
          body: "Open sentry.io → Issues for the API project. “SentryTestError” should appear within a minute.",
        });
      } else {
        const body = await response.json();
        setResult({ tone: "warning", title: "Nothing was sent", body: body.reason ?? "Sentry is off on the backend." });
      }
    } catch {
      setResult({ tone: "danger", title: "Could not reach the backend", body: "Is it running, or still waking up?" });
    }
  }

  function breakFrontend() {
    if (!frontendOn) {
      setResult({
        tone: "warning",
        title: "Nothing was sent",
        body: "Sentry is off on the screens (NEXT_PUBLIC_SENTRY_DSN was empty when they were built).",
      });
      return;
    }
    Sentry.captureException(new Error("Test error from the screens, sent on purpose from /debug-sentry."));
    setResult({
      tone: "success",
      title: "Screens test error sent",
      body: "Open sentry.io → Issues for the web project. The test error should appear within a minute.",
    });
  }

  const status = (on: boolean | null) => (on === null ? "checking…" : on ? "on" : "off");

  return (
    <AppShell>
      <PageHeader
        title="Error reporting test"
        intro="Each button causes an error on purpose, to check it shows up on the Sentry dashboard. Nothing about any family is sent."
      />
      <Card className="space-y-5">
        <p className="text-[17px]">
          Backend: <b>{status(backendOn)}</b> · Screens: <b>{status(frontendOn)}</b>
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" className={buttonSecondary} onClick={breakBackend}>
            Break the backend
          </button>
          <button type="button" className={buttonSecondary} onClick={breakFrontend}>
            Break the screens
          </button>
        </div>
        {result && (
          <Notice tone={result.tone} title={result.title} onClose={() => setResult(null)}>
            {result.body}
          </Notice>
        )}
      </Card>
    </AppShell>
  );
}
