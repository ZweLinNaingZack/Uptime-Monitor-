import { describe, expect, it } from "vitest";

import {
  formatCount,
  formatInterval,
  formatMs,
  formatPercent,
  formatRelativeTime,
  getMonitorStatus,
} from "@/lib/status";
import type { Check, Monitor } from "@/types";

const check: Check = {
  id: 1,
  monitorId: 1,
  statusCode: 200,
  responseMs: 50,
  isUp: true,
  error: null,
  checkedAt: "2026-01-01T00:00:00Z",
  duringMaintenance: false,
};

const monitor: Monitor = {
  id: 1,
  name: "Example",
  url: "https://example.com",
  intervalSeconds: 60,
  isActive: true,
  inMaintenance: false,
  createdAt: "2026-01-01T00:00:00Z",
  latestCheck: check,
};

describe("getMonitorStatus", () => {
  it("follows the latest check", () => {
    expect(getMonitorStatus(monitor)).toBe("up");
    expect(getMonitorStatus({ ...monitor, latestCheck: { ...check, isUp: false } })).toBe("down");
    expect(getMonitorStatus({ ...monitor, latestCheck: null })).toBe("pending");
  });

  it("puts paused before maintenance, and both before the check result", () => {
    expect(getMonitorStatus({ ...monitor, isActive: false, inMaintenance: true })).toBe("paused");
    expect(getMonitorStatus({ ...monitor, inMaintenance: true })).toBe("maintenance");
  });
});

describe("formatting", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");

  it.each([
    [2, "just now"],
    [45, "45s ago"],
    [300, "5m ago"],
    [7200, "2h ago"],
    [3 * 86400, "3d ago"],
  ])("%i seconds ago is %s", (seconds, text) => {
    expect(formatRelativeTime(new Date(now - seconds * 1000).toISOString(), now)).toBe(text);
  });

  it("never says a time is in the future", () => {
    expect(formatRelativeTime("2026-01-01T12:05:00Z", now)).toBe("just now");
  });

  it("formats numbers the same way on every computer", () => {
    expect(formatCount(8639)).toBe("8,639");
  });

  it("formats durations", () => {
    expect(formatMs(87)).toBe("87 ms");
    expect(formatMs(1534)).toBe("1.53 s");
    expect(formatMs(null)).toBe("—");
  });

  it("never rounds uptime up to 100%", () => {
    expect(formatPercent(99.996)).toBe("99.99%");
    expect(formatPercent(100)).toBe("100%");
    expect(formatPercent(null)).toBe("—");
  });

  it.each([
    [30, "30 seconds"],
    [60, "1 minute"],
    [300, "5 minutes"],
    [3600, "1 hour"],
    [86400, "1 day"],
    [90, "90 seconds"],
  ])("an interval of %i is %s", (seconds, text) => {
    expect(formatInterval(seconds)).toBe(text);
  });
});
