"use client";
// ^ This directive makes MonitorList a CLIENT Component: its code is sent to the browser,
// so it can use state (useState), effects (useEffect) and event handlers (onClick).
// Server Components (like app/page.tsx) can't do any of that, but they can fetch data
// before any JavaScript reaches the browser. The usual pattern, used here:
//   the Server Component fetches the first list  ->  passes it as a prop  ->
//   this Client Component takes over and keeps it fresh.
// Props passed from server to client must be serializable (plain JSON-like data).

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import MonitorCard from "@/components/MonitorCard";
import {
  checkMonitorNow,
  deleteMonitor,
  errorMessage,
  getMonitors,
  updateMonitor,
} from "@/lib/api";
import { useNow } from "@/lib/useNow";
import type { Monitor } from "@/types";

const POLL_INTERVAL_MS = 10_000;

interface MonitorListProps {
  /** Monitors fetched by the server, or null if the backend was unreachable. */
  initialMonitors: Monitor[] | null;
  /** Error message from the server-side fetch, if it failed. */
  initialError: string | null;
}

export default function MonitorList({ initialMonitors, initialError }: MonitorListProps) {
  // The props are only the *starting* value. From here on this component owns the list.
  const [monitors, setMonitors] = useState<Monitor[] | null>(initialMonitors);
  const [loadError, setLoadError] = useState<string | null>(initialError);
  const [actionError, setActionError] = useState<string | null>(null);
  // IDs of monitors with a request in flight, so we can disable their buttons.
  const [busyIds, setBusyIds] = useState<ReadonlySet<number>>(new Set());
  const now = useNow();

  /** Re-fetch the whole list from the backend. */
  const refresh = useCallback(() => {
    // State is only set inside the .then callbacks, i.e. when the response arrives,
    // never synchronously during the effect that calls refresh().
    return getMonitors().then(
      (fresh) => {
        setMonitors(fresh);
        setLoadError(null);
      },
      (error: unknown) => {
        // Keep showing the last known list, but tell the user it may be stale.
        setLoadError(errorMessage(error));
      },
    );
  }, []);

  // Keep the list fresh: refresh on (re)appearing, then poll every 10 seconds.
  //
  // Why refresh immediately, even though the server already fetched the list? With
  // Cache Components, Next.js keeps visited pages alive inside React's <Activity> instead
  // of unmounting them. When you go to "Add monitor" and come back, this component is
  // *shown again* with its OLD state; new props from the server don't reset useState.
  // Activity does clean up effects when hiding and re-run them when showing, so this
  // effect runs again every time the dashboard comes back into view.
  useEffect(() => {
    void refresh();

    const intervalId = setInterval(() => {
      // Don't poll while the browser tab is in the background: nobody is looking.
      if (document.visibilityState === "visible") void refresh();
    }, POLL_INTERVAL_MS);

    // When the user returns to this browser tab, update right away instead of waiting
    // up to 10 s for the next poll.
    function handleVisibilityChange() {
      if (document.visibilityState === "visible") void refresh();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    // Cleanup: runs when the component unmounts or is hidden by <Activity>. Forgetting
    // this would leave timers and listeners running forever, multiplying on every visit.
    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refresh]);

  function setBusy(id: number, busy: boolean) {
    // Always derive new state from the previous state (the `prev =>` form) and create a
    // NEW Set. React detects changes by reference; mutating the old Set would not re-render.
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function replaceMonitor(updated: Monitor) {
    setMonitors((prev) => prev?.map((m) => (m.id === updated.id ? updated : m)) ?? prev);
  }

  /** Runs an action for one monitor with busy-state and error handling around it. */
  async function runAction(monitor: Monitor, action: () => Promise<void>) {
    setBusy(monitor.id, true);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(`${monitor.name}: ${errorMessage(error)}`);
    } finally {
      setBusy(monitor.id, false);
    }
  }

  function handleCheckNow(monitor: Monitor) {
    void runAction(monitor, async () => {
      const check = await checkMonitorNow(monitor.id);
      setMonitors(
        (prev) => prev?.map((m) => (m.id === monitor.id ? { ...m, latestCheck: check } : m)) ?? prev,
      );
    });
  }

  function handleTogglePause(monitor: Monitor) {
    void runAction(monitor, async () => {
      replaceMonitor(await updateMonitor(monitor.id, { isActive: !monitor.isActive }));
    });
  }

  function handleDelete(monitor: Monitor) {
    if (!window.confirm(`Delete "${monitor.name}" and all of its check history?`)) return;
    void runAction(monitor, async () => {
      await deleteMonitor(monitor.id);
      setMonitors((prev) => prev?.filter((m) => m.id !== monitor.id) ?? prev);
    });
  }

  // ---------- Rendering: unreachable / empty / list ----------

  if (monitors === null) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        <h2 className="font-semibold">Can&apos;t load monitors</h2>
        <p className="mt-1 text-sm">{loadError ?? "The backend did not respond."}</p>
        <p className="mt-2 text-sm">
          Start it with <code className="font-mono">uvicorn app.main:app --reload</code> in the{" "}
          <code className="font-mono">backend</code> folder, then reload this page.
        </p>
      </div>
    );
  }

  if (monitors.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
        <h2 className="font-semibold">No monitors yet</h2>
        <p className="mt-1 text-sm text-zinc-500">Add a URL and we&apos;ll start checking it.</p>
        <Link
          href="/monitors/new"
          className="mt-4 inline-block rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Add your first monitor
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
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
      <ul className="space-y-4">
        {monitors.map((monitor) => (
          // `key` lets React match each card to the same monitor across re-renders.
          // Use a stable ID, never the array index.
          <MonitorCard
            key={monitor.id}
            monitor={monitor}
            now={now}
            busy={busyIds.has(monitor.id)}
            onCheckNow={handleCheckNow}
            onTogglePause={handleTogglePause}
            onDelete={handleDelete}
          />
        ))}
      </ul>
    </div>
  );
}
