// @vitest-environment jsdom
// The comment above gives this file a fake browser (jsdom), which rendering components needs.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CheckHistoryTable from "@/components/CheckHistoryTable";
import type { Check } from "@/types";

const checks: Check[] = [
  {
    id: 2,
    monitorId: 1,
    statusCode: 503,
    responseMs: 1534,
    isUp: false,
    error: "HTTP 503 Service Unavailable",
    checkedAt: "2026-01-01T12:01:00Z",
    duringMaintenance: true,
  },
  {
    id: 1,
    monitorId: 1,
    statusCode: null,
    responseMs: null,
    isUp: false,
    error: "Timed out after 10 seconds.",
    checkedAt: "2026-01-01T12:00:00Z",
    duringMaintenance: false,
  },
];

afterEach(cleanup);

describe("CheckHistoryTable", () => {
  it("shows one row per check with readable values", () => {
    render(<CheckHistoryTable checks={checks} now={Date.now()} />);
    expect(screen.getAllByRole("row")).toHaveLength(3); // the header plus two checks
    expect(screen.getByText("1.53 s")).toBeDefined();
    expect(screen.getByText("(maintenance)")).toBeDefined();
    expect(screen.getByText("Timed out after 10 seconds.")).toBeDefined();
  });

  it("waits for the browser before showing local times", () => {
    // During server rendering `now` is null: a time would use the server's timezone.
    render(<CheckHistoryTable checks={checks} now={null} />);
    expect(screen.getAllByText("…")).toHaveLength(2);
  });

  it("says so when there is no history", () => {
    render(<CheckHistoryTable checks={[]} now={null} />);
    expect(screen.getByText("No checks recorded yet.")).toBeDefined();
  });
});
