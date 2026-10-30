// TypeScript mirror of the backend's Pydantic schemas (backend/app/schemas.py).
// If you change a field there, change it here too. Field names are camelCase because the
// backend converts snake_case -> camelCase with a Pydantic alias_generator.
//
// Timestamps are ISO 8601 strings in UTC ending in "Z" (e.g. "2026-10-29T16:03:59.662Z").
// JSON has no Date type, so we keep them as strings and convert with `new Date(...)`
// only where we display them, in the browser, in the user's own timezone.

export interface Check {
  id: number;
  monitorId: number;
  statusCode: number | null; // null = no HTTP response at all (timeout, refused, DNS...)
  responseMs: number | null;
  isUp: boolean;
  error: string | null;
  checkedAt: string;
}

export interface Monitor {
  id: number;
  name: string;
  url: string;
  intervalSeconds: number;
  isActive: boolean;
  createdAt: string;
  latestCheck: Check | null; // null until the first check has finished
}

// Request bodies
export interface MonitorCreateInput {
  name: string;
  url: string;
  intervalSeconds: number;
}

export interface MonitorUpdateInput {
  isActive: boolean;
}

// What the dashboard shows for a monitor. Derived from Monitor in one place
// (getMonitorStatus in lib/status.ts) so every component agrees.
export type MonitorStatus = "up" | "down" | "paused" | "pending";
