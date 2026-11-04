// Small pure helpers for displaying monitors. "Pure" = same input, same output, no side
// effects, which makes them safe to call from both Server and Client Components.

import type { Monitor, MonitorStatus } from "@/types";

export function getMonitorStatus(monitor: Monitor): MonitorStatus {
  if (!monitor.isActive) return "paused";
  if (monitor.inMaintenance) return "maintenance";
  if (monitor.latestCheck === null) return "pending";
  return monitor.latestCheck.isUp ? "up" : "down";
}

/** 45 -> "45s ago", 300 -> "5m ago", 7200 -> "2h ago". */
export function formatRelativeTime(isoTimestamp: string, nowMs: number): string {
  const seconds = Math.max(0, Math.round((nowMs - new Date(isoTimestamp).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// A FIXED locale, on purpose. `n.toLocaleString()` would use the server's locale during
// server rendering ("1,234") and the browser's during hydration (maybe "1.234" in
// Germany): different text, so React reports a hydration mismatch.
const countFormat = new Intl.NumberFormat("en-US");

/** 8639 -> "8,639". */
export function formatCount(n: number): string {
  return countFormat.format(n);
}

/** 87 -> "87 ms", 1534 -> "1.53 s", null -> "—". */
export function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** 99.95 -> "99.95%", 100 -> "100%", null -> "—". */
export function formatPercent(value: number | null): string {
  if (value === null) return "—";
  // Never round 99.996 up to "100%": that would hide real downtime.
  const floored = Math.floor(value * 100) / 100;
  return `${floored}%`;
}

/** 30 -> "30 seconds", 60 -> "1 minute", 3600 -> "1 hour". */
export function formatInterval(seconds: number): string {
  const units: [number, string][] = [
    [86_400, "day"],
    [3_600, "hour"],
    [60, "minute"],
  ];
  for (const [size, name] of units) {
    if (seconds >= size && seconds % size === 0) {
      const n = seconds / size;
      return `${n} ${name}${n === 1 ? "" : "s"}`;
    }
  }
  return `${seconds} seconds`;
}
