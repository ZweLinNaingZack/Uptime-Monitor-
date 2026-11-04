// The most recent checks as a table: every raw value the chart summarises is readable
// here without hovering. Presentational.

import { formatMs } from "@/lib/status";
import type { Check } from "@/types";

interface CheckHistoryTableProps {
  checks: Check[];
  /** From useNow(): null during server render/hydration, when we can't format times yet. */
  now: number | null;
}

export default function CheckHistoryTable({ checks, now }: CheckHistoryTableProps) {
  if (checks.length === 0) {
    return <p className="text-sm text-zinc-500">No checks recorded yet.</p>;
  }

  return (
    // overflow-x-auto: on a narrow phone the table scrolls sideways inside its box
    // instead of making the whole page wider than the screen.
    <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
          <tr>
            <th scope="col" className="px-4 py-2 font-medium">Time</th>
            <th scope="col" className="px-4 py-2 font-medium">Result</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">HTTP</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Response</th>
            <th scope="col" className="px-4 py-2 font-medium">Error</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 tabular-nums dark:divide-zinc-800">
          {checks.map((check) => (
            <tr key={check.id}>
              <td className="whitespace-nowrap px-4 py-2">
                {/* Local time only exists in the browser. Rendering it on the server would
                    use the SERVER's timezone and cause a hydration mismatch. */}
                {now === null ? "…" : new Date(check.checkedAt).toLocaleString()}
              </td>
              <td className="px-4 py-2">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: check.isUp ? "var(--status-good)" : "var(--status-critical)" }}
                    aria-hidden="true"
                  />
                  {check.isUp ? "Up" : "Down"}
                  {check.duringMaintenance && <span className="text-zinc-500">(maintenance)</span>}
                </span>
              </td>
              <td className="px-4 py-2 text-right">{check.statusCode ?? "—"}</td>
              <td className="px-4 py-2 text-right">{formatMs(check.responseMs)}</td>
              <td className="max-w-xs truncate px-4 py-2 text-zinc-500" title={check.error ?? undefined}>
                {check.error ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
