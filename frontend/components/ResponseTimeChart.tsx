"use client";
// A hand-drawn SVG chart: average response time per time bucket (the line), plus a strip
// underneath showing whether any check in each bucket failed.
//
// Why no chart library? This chart is ~250 lines and every pixel is visible in the code:
// scales are just arithmetic, the line is one SVG <path>, the hover is one event handler.
// Reading it teaches what libraries like Recharts or D3 do for you. For many chart types
// in a real product, a library is usually the better choice.
//
// Why a Client Component? It measures its own width (ResizeObserver), tracks the hovered
// bucket in state, and formats times in the user's timezone. All of that needs the browser.

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { formatCount, formatMs } from "@/lib/status";
import type { MonitorStats, StatsBucket } from "@/types";

// Layout in pixels. The plot is the area inside the margins.
const MARGIN = { top: 12, right: 12, bottom: 24, left: 60 };
const PLOT_HEIGHT = 170;
const STRIP_GAP = 10; // space between the line plot and the status strip
const STRIP_HEIGHT = 10;
const SVG_HEIGHT = MARGIN.top + PLOT_HEIGHT + STRIP_GAP + STRIP_HEIGHT + MARGIN.bottom;
const Y_TICKS = 4;

/** Round up to a "nice" number for the top of the y-axis: 137 -> 200, 420 -> 500, 1234 -> 2000. */
function niceCeil(value: number): number {
  if (value <= 0) return 100;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const fraction = value / magnitude;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * magnitude;
}

function formatTick(iso: string, periodHours: number): string {
  // Runs only in the browser (the chart renders nothing until it has measured its
  // width), so using the user's locale and timezone here can't cause a hydration mismatch.
  const date = new Date(iso);
  return periodHours <= 24
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatRange(bucket: StatsBucket): string {
  const options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  };
  return `${new Date(bucket.start).toLocaleString([], options)} – ${new Date(bucket.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function stripColor(bucket: StatsBucket): string {
  if (bucket.totalChecks === 0) return "var(--chart-no-data)";
  return bucket.downChecks > 0 ? "var(--status-critical)" : "var(--status-good)";
}

/** Turn the bucket averages into an SVG path, starting a new segment after each gap. */
function buildLinePath(points: ({ x: number; y: number } | null)[]): string {
  let d = "";
  let penDown = false;
  for (const point of points) {
    if (point === null) {
      penDown = false; // no data here: lift the pen so the line shows a gap, not a dip to 0
      continue;
    }
    d += `${penDown ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)} `;
    penDown = true;
  }
  return d.trim();
}

export default function ResponseTimeChart({ stats }: { stats: MonitorStats }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Measure the container and re-measure whenever it resizes (window resize, phone
  // rotation). SVG needs real pixel numbers; percentages don't work for path coordinates.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const { buckets } = stats;
  const count = buckets.length;

  return (
    <div ref={containerRef} className="relative w-full" style={{ height: SVG_HEIGHT }}>
      {width !== null && count > 0 && (
        <ChartBody
          stats={stats}
          width={width}
          activeIndex={activeIndex}
          onActiveIndexChange={setActiveIndex}
        />
      )}
    </div>
  );
}

interface ChartBodyProps {
  stats: MonitorStats;
  width: number;
  activeIndex: number | null;
  onActiveIndexChange: (index: number | null) => void;
}

function ChartBody({ stats, width, activeIndex, onActiveIndexChange }: ChartBodyProps) {
  const { buckets, periodHours } = stats;
  const count = buckets.length;
  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 10);
  const slotWidth = plotWidth / count;

  // ---------- Scales: data value -> pixel position ----------
  const maxAvg = Math.max(0, ...buckets.map((b) => b.avgResponseMs ?? 0));
  const yMax = niceCeil(maxAvg);
  const x = (index: number) => MARGIN.left + (index + 0.5) * slotWidth; // centre of a slot
  // SVG's y axis points DOWN, so a bigger value means a smaller y.
  const y = (ms: number) => MARGIN.top + PLOT_HEIGHT - (ms / yMax) * PLOT_HEIGHT;

  const points = buckets.map((b, i) => (b.avgResponseMs === null ? null : { x: x(i), y: y(b.avgResponseMs) }));
  const linePath = buildLinePath(points);
  // A point with gaps on both sides is invisible as a path (a line needs two points),
  // so draw those as small dots.
  const isolated = points.filter(
    (p, i): p is { x: number; y: number } => p !== null && !points[i - 1] && !points[i + 1],
  );

  const yTicks = Array.from({ length: Y_TICKS + 1 }, (_, i) => (yMax / Y_TICKS) * i);
  const labelCount = Math.max(2, Math.min(6, Math.floor(plotWidth / 90)));
  const xLabelIndexes = Array.from({ length: labelCount }, (_, i) =>
    Math.round((i * (count - 1)) / (labelCount - 1)),
  );
  const stripTop = MARGIN.top + PLOT_HEIGHT + STRIP_GAP;

  // ---------- Interaction ----------
  // The crosshair snaps to the nearest bucket, so the reader aims at a time, not at a
  // 2px line. The hit area is the whole plot, much bigger than the line itself.
  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const index = Math.floor((event.clientX - rect.left - MARGIN.left) / slotWidth);
    onActiveIndexChange(Math.min(Math.max(index, 0), count - 1));
  }

  // Keyboard users get the same readout: focus the chart, then use the arrow keys.
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault(); // don't scroll the page
    const step = event.key === "ArrowLeft" ? -1 : 1;
    const current = activeIndex ?? count - 1;
    onActiveIndexChange(Math.min(Math.max(current + step, 0), count - 1));
  }

  const active = activeIndex === null ? null : buckets[activeIndex];
  const activePoint = activeIndex === null ? null : points[activeIndex];

  return (
    <div
      tabIndex={0}
      role="group"
      aria-label={`Average response time and failed checks, last ${periodHours} hours. Use the left and right arrow keys to read values.`}
      onKeyDown={handleKeyDown}
      onFocus={() => onActiveIndexChange(activeIndex ?? count - 1)}
      onBlur={() => onActiveIndexChange(null)}
      className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
    >
      <svg
        width={width}
        height={SVG_HEIGHT}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => onActiveIndexChange(null)}
        className="block touch-none select-none"
        aria-hidden="true" // the tooltip below carries the text for screen readers
      >
        {/* Gridlines + y-axis labels: thin and pale so the data stands out. */}
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={MARGIN.left}
              x2={MARGIN.left + plotWidth}
              y1={y(tick)}
              y2={y(tick)}
              stroke={tick === 0 ? "var(--chart-axis)" : "var(--chart-grid)"}
              strokeWidth={1}
            />
            <text
              x={MARGIN.left - 8}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--chart-muted)"
              className="tabular-nums"
            >
              {formatMs(tick)}
            </text>
          </g>
        ))}

        {/* The data: one 2px line, gaps where nothing responded. */}
        <path
          d={linePath}
          fill="none"
          stroke="var(--chart-series)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {isolated.map((p) => (
          <circle key={`${p.x}`} cx={p.x} cy={p.y} r={2.5} fill="var(--chart-series)" />
        ))}

        {/* Status strip: one cell per bucket, with a 2px gap between cells. */}
        <text x={MARGIN.left - 8} y={stripTop + STRIP_HEIGHT / 2} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--chart-muted)">
          Status
        </text>
        {buckets.map((bucket, i) => (
          <rect
            key={bucket.start}
            x={MARGIN.left + i * slotWidth + 1}
            y={stripTop}
            width={Math.max(slotWidth - 2, 1)}
            height={STRIP_HEIGHT}
            rx={Math.min(2, slotWidth / 4)}
            fill={stripColor(bucket)}
            opacity={activeIndex === null || activeIndex === i ? 1 : 0.55}
          />
        ))}

        {/* x-axis labels */}
        {xLabelIndexes.map((index, i) => (
          <text
            key={index}
            x={x(index)}
            y={SVG_HEIGHT - 6}
            // Keep the first and last labels inside the chart instead of half cut off.
            textAnchor={i === 0 ? "start" : i === xLabelIndexes.length - 1 ? "end" : "middle"}
            fontSize={11}
            fill="var(--chart-muted)"
          >
            {formatTick(buckets[index].start, periodHours)}
          </text>
        ))}

        {/* Hover layer: vertical crosshair + a dot on the line. */}
        {activeIndex !== null && (
          <g pointerEvents="none">
            <line
              x1={x(activeIndex)}
              x2={x(activeIndex)}
              y1={MARGIN.top}
              y2={stripTop + STRIP_HEIGHT}
              stroke="var(--chart-axis)"
              strokeWidth={1}
            />
            {activePoint && (
              // The 2px ring in the surface colour keeps the dot readable on top of the line.
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r={4.5}
                fill="var(--chart-series)"
                stroke="var(--chart-surface)"
                strokeWidth={2}
              />
            )}
          </g>
        )}
      </svg>

      {active && activeIndex !== null && (
        <Tooltip bucket={active} left={x(activeIndex)} chartWidth={width} />
      )}
    </div>
  );
}

function Tooltip({ bucket, left, chartWidth }: { bucket: StatsBucket; left: number; chartWidth: number }) {
  const TOOLTIP_WIDTH = 200;
  // Keep the box inside the chart near the left/right edges.
  const clampedLeft = Math.min(Math.max(left - TOOLTIP_WIDTH / 2, 0), chartWidth - TOOLTIP_WIDTH);

  return (
    <div
      role="status" // screen readers announce the new values as the user moves along
      className="pointer-events-none absolute top-0 z-10 rounded-md border border-zinc-200 bg-white p-2.5 text-xs shadow-md dark:border-zinc-700 dark:bg-zinc-900"
      style={{ left: clampedLeft, width: TOOLTIP_WIDTH }}
    >
      <p className="text-zinc-500">{formatRange(bucket)}</p>
      {bucket.totalChecks === 0 ? (
        <p className="mt-1 font-medium">No checks</p>
      ) : (
        <>
          {/* Value first and strongest; the series name follows in muted ink. */}
          <p className="mt-1.5 flex items-center gap-2">
            <span className="inline-block h-0.5 w-3 rounded" style={{ background: "var(--chart-series)" }} aria-hidden="true" />
            <span className="text-sm font-semibold tabular-nums">{formatMs(bucket.avgResponseMs)}</span>
            <span className="text-zinc-500">average</span>
          </p>
          {bucket.maxResponseMs !== null && (
            <p className="mt-0.5 pl-5 text-zinc-500 tabular-nums">slowest {formatMs(bucket.maxResponseMs)}</p>
          )}
          <p className="mt-1.5 flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: stripColor(bucket) }} aria-hidden="true" />
            <span className="tabular-nums">
              {bucket.downChecks === 0
                ? `All ${formatCount(bucket.totalChecks)} checks up`
                : `${formatCount(bucket.downChecks)} of ${formatCount(bucket.totalChecks)} checks down`}
            </span>
          </p>
        </>
      )}
    </div>
  );
}
