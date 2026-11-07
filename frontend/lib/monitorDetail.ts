// Data loading for the monitor detail page, shared by the Server Component
// (app/monitors/[id]/page.tsx) and the Client Component (components/MonitorDetail.tsx).
//
// Why a separate file? Anything exported from a "use client" file becomes a *client
// reference* when a Server Component imports it: fine for rendering a component, but
// a plain function or constant imported that way can't be called on the server. Code
// that both sides need lives in a module without "use client".

import { getChecks, getMonitor, getMonitorStats, type RequestAuth } from "@/lib/api";
import type { Check, Monitor, MonitorStats } from "@/types";

export const PERIODS = [
  { hours: 24, label: "24 hours" },
  { hours: 24 * 7, label: "7 days" },
  { hours: 24 * 30, label: "30 days" },
] as const;

export const DEFAULT_PERIOD_HOURS = PERIODS[0].hours;
const HISTORY_LIMIT = 100;

/** Everything the page shows, fetched together so the numbers always agree. */
export interface MonitorDetailData {
  monitor: Monitor;
  stats: MonitorStats;
  checks: Check[];
}

export function fetchMonitorDetail(
  id: number,
  hours: number,
  auth?: RequestAuth,
): Promise<MonitorDetailData> {
  // Promise.all starts the three requests at the same time instead of one after another.
  return Promise.all([
    getMonitor(id, auth),
    getMonitorStats(id, hours, auth),
    getChecks(id, HISTORY_LIMIT, auth),
  ]).then(([monitor, stats, checks]) => ({ monitor, stats, checks }));
}
