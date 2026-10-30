// A *presentational* component: it only displays what it receives through props and
// reports clicks through callbacks (onCheckNow, ...). It owns no state and fetches
// nothing. Its parent, MonitorList, decides what those clicks actually do.
//
// There is no "use client" at the top, yet this still runs in the browser: any component
// imported by a Client Component (MonitorList) becomes part of the client bundle too.
// "use client" marks the *entry point* of client code, not every client file.

import { formatInterval, formatRelativeTime, getMonitorStatus } from "@/lib/status";
import type { Monitor, MonitorStatus } from "@/types";

const BADGE_STYLES: Record<MonitorStatus, { label: string; className: string }> = {
  up: { label: "Up", className: "bg-green-100 text-green-800 ring-green-600/20" },
  down: { label: "Down", className: "bg-red-100 text-red-800 ring-red-600/20" },
  paused: { label: "Paused", className: "bg-zinc-100 text-zinc-700 ring-zinc-500/20" },
  pending: { label: "Pending", className: "bg-amber-100 text-amber-800 ring-amber-600/20" },
};

const DOT_STYLES: Record<MonitorStatus, string> = {
  up: "bg-green-500",
  down: "bg-red-500",
  paused: "bg-zinc-400",
  pending: "bg-amber-500 animate-pulse",
};

function StatusBadge({ status }: { status: MonitorStatus }) {
  const { label, className } = BADGE_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${DOT_STYLES[status]}`} aria-hidden="true" />
      {label}
    </span>
  );
}

interface MonitorCardProps {
  monitor: Monitor;
  /** Current time from useNow(); null during server render/hydration. */
  now: number | null;
  /** True while an action for this monitor is in flight (disables the buttons). */
  busy: boolean;
  onCheckNow: (monitor: Monitor) => void;
  onTogglePause: (monitor: Monitor) => void;
  onDelete: (monitor: Monitor) => void;
}

export default function MonitorCard({
  monitor,
  now,
  busy,
  onCheckNow,
  onTogglePause,
  onDelete,
}: MonitorCardProps) {
  const status = getMonitorStatus(monitor);
  const check = monitor.latestCheck;

  return (
    <li className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate font-semibold">{monitor.name}</h2>
            <StatusBadge status={status} />
          </div>
          {/* rel="noreferrer" stops the opened site from seeing or controlling this tab. */}
          <a
            href={monitor.url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-sm text-zinc-500 hover:underline"
          >
            {monitor.url}
          </a>
        </div>

        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => onCheckNow(monitor)}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Check now
          </button>
          <button
            type="button"
            onClick={() => onTogglePause(monitor)}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            {monitor.isActive ? "Pause" : "Resume"}
          </button>
          <button
            type="button"
            onClick={() => onDelete(monitor)}
            disabled={busy}
            className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950"
          >
            Delete
          </button>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Stat label="Response time" value={check?.responseMs != null ? `${check.responseMs} ms` : "—"} />
        <Stat label="HTTP status" value={check?.statusCode != null ? String(check.statusCode) : "—"} />
        <Stat
          label="Last check"
          value={
            check === null
              ? "Never"
              : now === null
                ? "…" // the time is only known after hydration (see lib/useNow.ts)
                : formatRelativeTime(check.checkedAt, now)
          }
          // Hovering shows the exact time in the user's own timezone (browser only).
          title={check && now !== null ? new Date(check.checkedAt).toLocaleString() : undefined}
        />
        <Stat label="Interval" value={`Every ${formatInterval(monitor.intervalSeconds)}`} />
      </dl>

      {check?.error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-300">
          {check.error}
        </p>
      )}
    </li>
  );
}

function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="font-medium tabular-nums" title={title}>
        {value}
      </dd>
    </div>
  );
}
