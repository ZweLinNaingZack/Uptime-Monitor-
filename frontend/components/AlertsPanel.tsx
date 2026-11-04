"use client";
// The interactive part of /alerts. Channels are set up in backend/.env, not here. There is
// no login yet, so a form that saved webhook URLs would let anyone who can reach the
// server redirect your alerts. This page can only show the status and send a test.

import Link from "next/link";
import { useCallback, useState } from "react";

import { errorMessage, getAlertChannels, getAlertEvents, sendTestAlert } from "@/lib/api";
import { useNow } from "@/lib/useNow";
import { usePolling } from "@/lib/usePolling";
import type { AlertChannel, AlertEvent, AlertEventStatus, AlertTestResult } from "@/types";

const POLL_INTERVAL_MS = 10_000;

const CHANNEL_LABELS: Record<string, string> = { discord: "Discord", telegram: "Telegram" };

const STATUS_LABELS: Record<AlertEventStatus, string> = {
  pending: "Sending…",
  sent: "Sent",
  partial: "Partly sent",
  failed: "Failed",
  no_channels: "Not sent: no channel set up",
};

interface AlertsPanelProps {
  initialChannels: AlertChannel[] | null;
  initialEvents: AlertEvent[];
  initialError: string | null;
}

export default function AlertsPanel({ initialChannels, initialEvents, initialError }: AlertsPanelProps) {
  const now = useNow();
  const [channels, setChannels] = useState(initialChannels);
  const [events, setEvents] = useState(initialEvents);
  const [loadError, setLoadError] = useState(initialError);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<AlertTestResult[] | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void Promise.all([getAlertChannels(), getAlertEvents()]).then(
      ([freshChannels, freshEvents]) => {
        setChannels(freshChannels);
        setEvents(freshEvents);
        setLoadError(null);
      },
      (error: unknown) => setLoadError(errorMessage(error)),
    );
  }, []);

  usePolling(refresh, POLL_INTERVAL_MS);

  async function handleTest() {
    setTesting(true);
    setTestResults(null);
    setTestError(null);
    try {
      setTestResults(await sendTestAlert());
    } catch (error) {
      setTestError(errorMessage(error));
    } finally {
      setTesting(false);
    }
  }

  if (channels === null) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        <h2 className="font-semibold">Can&apos;t load alerts</h2>
        <p className="mt-1 text-sm">{loadError ?? "The backend did not respond."}</p>
        <p className="mt-2 text-sm">This page retries automatically every 10 seconds.</p>
      </div>
    );
  }

  const anyConfigured = channels.some((channel) => channel.configured);

  return (
    <div className="space-y-8">
      {loadError && (
        <p role="status" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Couldn&apos;t refresh, showing the last known data. {loadError}
        </p>
      )}

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">Channels</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {channels.map((channel) => (
                <li key={channel.name} className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: channel.configured ? "var(--status-good)" : "var(--chart-axis)" }}
                    aria-hidden="true"
                  />
                  {CHANNEL_LABELS[channel.name] ?? channel.name}:{" "}
                  <span className="text-zinc-500">{channel.configured ? "set up" : "not set up"}</span>
                </li>
              ))}
            </ul>
          </div>
          <button
            type="button"
            onClick={() => void handleTest()}
            disabled={testing || !anyConfigured}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            {testing ? "Sending…" : "Send test alert"}
          </button>
        </div>

        {!anyConfigured && (
          <p className="mt-3 text-sm text-zinc-500">
            Alerts are still recorded below, but nothing is sent. Add a Discord webhook or Telegram
            bot to <code className="font-mono">backend/.env</code> and restart the backend. The
            README section &quot;Setting up alerts&quot; has the steps.
          </p>
        )}

        {testError && (
          <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">{testError}</p>
        )}
        {testResults && (
          <ul role="status" className="mt-3 space-y-1 text-sm">
            {testResults.map((result) => (
              <li key={result.channel}>
                {CHANNEL_LABELS[result.channel] ?? result.channel}:{" "}
                {result.ok ? "accepted the test message. Check that it arrived." : `failed (${result.error}). Check its settings in backend/.env.`}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 font-semibold">History</h2>
        {events.length === 0 ? (
          <p className="text-sm text-zinc-500">No alerts yet. That&apos;s a good thing.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Time</th>
                  <th scope="col" className="px-4 py-2 font-medium">Monitor</th>
                  <th scope="col" className="px-4 py-2 font-medium">Event</th>
                  <th scope="col" className="px-4 py-2 font-medium">Delivery</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums">
                      {/* Local time exists only in the browser: see lib/useNow.ts. */}
                      {now === null ? "…" : new Date(event.createdAt).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">
                      <Link href={`/monitors/${event.monitorId}`} className="hover:underline">
                        {event.monitorName}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ background: event.kind === "down" ? "var(--status-critical)" : "var(--status-good)" }}
                          aria-hidden="true"
                        />
                        {event.kind === "down" ? "Down" : "Recovered"}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      {STATUS_LABELS[event.status]}
                      {event.error && <span className="block text-xs text-zinc-500">{event.error}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
