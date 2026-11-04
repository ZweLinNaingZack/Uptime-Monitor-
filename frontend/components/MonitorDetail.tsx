"use client";
// The interactive part of /monitors/[id]. Same pattern as the dashboard: the Server
// Component (app/monitors/[id]/page.tsx) fetches the first data, this component takes over,
// polls, and handles the buttons.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import CheckHistoryTable from "@/components/CheckHistoryTable";
import MonitorCard from "@/components/MonitorCard";
import ResponseTimeChart from "@/components/ResponseTimeChart";
import StatTiles from "@/components/StatTiles";
import { ApiError, checkMonitorNow, deleteMonitor, errorMessage, updateMonitor } from "@/lib/api";
import {
  DEFAULT_PERIOD_HOURS,
  fetchMonitorDetail,
  PERIODS,
  type MonitorDetailData,
} from "@/lib/monitorDetail";
import { useNow } from "@/lib/useNow";
import { usePolling } from "@/lib/usePolling";
import type { Monitor } from "@/types";

const POLL_INTERVAL_MS = 10_000;

interface MonitorDetailProps {
  monitorId: number;
  initialData: MonitorDetailData | null;
  initialError: string | null;
}

export default function MonitorDetail({ monitorId, initialData, initialError }: MonitorDetailProps) {
  const router = useRouter();
  const now = useNow();
  const [data, setData] = useState<MonitorDetailData | null>(initialData);
  const [hours, setHours] = useState<number>(DEFAULT_PERIOD_HOURS);
  const [loadError, setLoadError] = useState<string | null>(initialError);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleted, setDeleted] = useState(false);

  // Each refresh gets a number. If you click "7 days" and then "30 days" quickly, the
  // 7-day response might arrive LAST; without this check it would overwrite the 30-day
  // data. A ref (unlike state) changes without re-rendering, perfect for a counter.
  const latestRequest = useRef(0);

  // Recreated when `hours` changes, which restarts usePolling and fetches immediately.
  const refresh = useCallback(() => {
    const requestId = ++latestRequest.current;
    void fetchMonitorDetail(monitorId, hours).then(
      (fresh) => {
        if (requestId !== latestRequest.current) return; // a newer request superseded this one
        setData(fresh);
        setLoadError(null);
      },
      (error: unknown) => {
        if (requestId !== latestRequest.current) return;
        if (error instanceof ApiError && error.status === 404) {
          setDeleted(true); // deleted elsewhere (e.g. in another tab)
          return;
        }
        setLoadError(errorMessage(error));
      },
    );
  }, [monitorId, hours]);

  usePolling(refresh, POLL_INTERVAL_MS);

  // While a new period loads, keep showing the old one, faded ("refetch keeps the frame").
  // No skeleton, no layout jump. We know the data is stale when its period differs.
  const isSwitchingPeriod = data !== null && data.stats.periodHours !== hours;

  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function handleCheckNow() {
    void runAction(async () => {
      await checkMonitorNow(monitorId);
      refresh(); // the new check changes the stats, the chart and the table
    });
  }

  function handleTogglePause(monitor: Monitor) {
    void runAction(async () => {
      const updated = await updateMonitor(monitorId, { isActive: !monitor.isActive });
      setData((prev) => (prev ? { ...prev, monitor: updated } : prev));
    });
  }

  function handleToggleMaintenance(monitor: Monitor) {
    void runAction(async () => {
      const updated = await updateMonitor(monitorId, { inMaintenance: !monitor.inMaintenance });
      setData((prev) => (prev ? { ...prev, monitor: updated } : prev));
    });
  }

  function handleDelete(monitor: Monitor) {
    if (!window.confirm(`Delete "${monitor.name}" and all of its check history?`)) return;
    void runAction(async () => {
      await deleteMonitor(monitorId);
      router.push("/");
    });
  }

  if (deleted) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
        <h2 className="font-semibold">This monitor no longer exists</h2>
        <Link href="/" className="mt-3 inline-block text-sm underline">
          Back to all monitors
        </Link>
      </div>
    );
  }

  if (data === null) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        <h2 className="font-semibold">Can&apos;t load this monitor</h2>
        <p className="mt-1 text-sm">{loadError ?? "The backend did not respond."}</p>
        <p className="mt-2 text-sm">This page retries automatically every 10 seconds.</p>
      </div>
    );
  }

  const { monitor, stats, checks } = data;

  return (
    <div className="space-y-6">
      {loadError && (
        <p role="status" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Couldn&apos;t refresh, showing the last known data. {loadError}
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-300">
          {actionError}
        </p>
      )}

      {/* Reusing the dashboard card: it is presentational, so it works anywhere. */}
      <ul>
        <MonitorCard
          monitor={monitor}
          now={now}
          busy={busy}
          onCheckNow={handleCheckNow}
          onTogglePause={handleTogglePause}
          onToggleMaintenance={handleToggleMaintenance}
          onDelete={handleDelete}
        />
      </ul>

      {monitor.inMaintenance && (
        <p role="status" className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:bg-blue-950 dark:text-blue-200">
          In maintenance: checks continue, but alerts are silenced and results don&apos;t count
          towards uptime.
        </p>
      )}

      {/* Filters go in one row ABOVE everything they affect: tiles, chart and table all
          use the same period, so their numbers always agree. */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-zinc-500">Period</span>
        <div role="radiogroup" aria-label="Statistics period" className="inline-flex rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700">
          {PERIODS.map((period) => (
            <button
              key={period.hours}
              type="button"
              role="radio"
              aria-checked={hours === period.hours}
              onClick={() => setHours(period.hours)}
              className={`rounded px-3 py-1 text-sm ${
                hours === period.hours
                  ? "bg-zinc-900 font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
                  : "hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
        {isSwitchingPeriod && <span className="text-sm text-zinc-500">Loading…</span>}
      </div>

      <div className={`space-y-6 transition-opacity ${isSwitchingPeriod ? "opacity-50" : ""}`}>
        <StatTiles stats={stats} />

        <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold">Response time</h2>
            <ChartLegend />
          </div>
          <ResponseTimeChart stats={stats} />
          <p className="mt-2 text-xs text-zinc-500">
            Checks made during maintenance are left out of these numbers.
          </p>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-semibold">Recent checks</h2>
        <CheckHistoryTable checks={checks} now={now} />
      </section>
    </div>
  );
}

/** Colour is never the only clue: every swatch has a text label next to it. */
function ChartLegend() {
  const items = [
    { label: "Average response", swatch: <span className="inline-block h-0.5 w-4 rounded" style={{ background: "var(--chart-series)" }} /> },
    { label: "All up", swatch: <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--status-good)" }} /> },
    { label: "Some down", swatch: <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--status-critical)" }} /> },
    { label: "No data", swatch: <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--chart-no-data)" }} /> },
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-flex">{item.swatch}</span>
          {item.label}
        </li>
      ))}
    </ul>
  );
}
