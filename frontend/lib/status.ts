// Small pure helpers for displaying monitors. "Pure" = same input, same output, no side
// effects, which makes them safe to call from both Server and Client Components.

import type { Monitor, MonitorStatus } from "@/types";

export function getMonitorStatus(monitor: Monitor): MonitorStatus {
  if (!monitor.isActive) return "paused";
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
