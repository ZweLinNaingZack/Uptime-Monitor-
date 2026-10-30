// A row of headline numbers for the selected period. Presentational: data in, markup out.
//
// Why tiles and not a chart? A single value ("99.9% uptime") is best shown as a number.
// Drawing a one-bar chart for it would only make it harder to read.

import { formatCount, formatMs, formatPercent } from "@/lib/status";
import type { MonitorStats } from "@/types";

export default function StatTiles({ stats }: { stats: MonitorStats }) {
  const tiles = [
    {
      label: "Uptime",
      value: formatPercent(stats.uptimePercent),
      detail:
        stats.totalChecks === 0
          ? "No checks in this period"
          : `${formatCount(stats.upChecks)} of ${formatCount(stats.totalChecks)} checks up`,
    },
    {
      label: "Average response",
      value: formatMs(stats.avgResponseMs),
      detail:
        stats.minResponseMs !== null && stats.maxResponseMs !== null
          ? `${formatMs(stats.minResponseMs)} – ${formatMs(stats.maxResponseMs)}`
          : "No responses yet",
    },
    {
      label: "95th percentile",
      value: formatMs(stats.p95ResponseMs),
      // The average hides slow outliers; p95 shows how slow the worst 5% were.
      detail: "95% of responses were this fast or faster",
    },
    {
      label: "Failed checks",
      value: formatCount(stats.downChecks),
      detail: stats.downChecks === 1 ? "1 check down" : `${formatCount(stats.downChecks)} checks down`,
    },
  ];

  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <dt className="text-sm text-zinc-500">{tile.label}</dt>
          <dd className="mt-1 text-2xl font-semibold">{tile.value}</dd>
          <dd className="mt-1 text-xs text-zinc-500">{tile.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
