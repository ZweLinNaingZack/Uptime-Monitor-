// /alerts: which channels are set up, a test button, and the history of sent alerts.
// Same shape as the dashboard: a static shell, with the uncached data inside <Suspense>.

import type { Metadata } from "next";
import { Suspense } from "react";

import AlertsPanel from "@/components/AlertsPanel";
import { errorMessage, getAlertChannels, getAlertEvents } from "@/lib/api";
import { forwardedAuth, redirectIfLoggedOut } from "@/lib/serverAuth";
import type { AlertChannel, AlertEvent } from "@/types";

export const metadata: Metadata = {
  title: "Alerts · Uptime Monitor",
};

export default function AlertsPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Alerts</h1>
      <p className="mt-1 text-sm text-zinc-500">
        You get a message when a monitor goes down and when it recovers.
      </p>
      <div className="mt-6">
        <Suspense fallback={<AlertsSkeleton />}>
          <AlertsLoader />
        </Suspense>
      </div>
    </div>
  );
}

async function AlertsLoader() {
  let channels: AlertChannel[] | null = null;
  let events: AlertEvent[] = [];
  let error: string | null = null;
  try {
    const auth = await forwardedAuth();
    [channels, events] = await Promise.all([getAlertChannels(auth), getAlertEvents(undefined, auth)]);
  } catch (e) {
    redirectIfLoggedOut(e);
    error = errorMessage(e); // backend down: the client component shows it and retries
  }
  return <AlertsPanel initialChannels={channels} initialEvents={events} initialError={error} />;
}

function AlertsSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-busy="true" aria-label="Loading alerts">
      <div className="h-32 rounded-lg bg-zinc-200 dark:bg-zinc-800" />
      <div className="h-64 rounded-lg bg-zinc-200 dark:bg-zinc-800" />
    </div>
  );
}
