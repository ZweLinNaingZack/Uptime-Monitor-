"""Statistics for one monitor over a time window: uptime %, response times, chart buckets.

Like checker.py, this module is "pure": it receives plain data (the checks in the
window) and returns plain data. It never touches the database or the network, which
makes it easy to read and to test with hand-made inputs.

Why compute in Python instead of SQL?
    Counts and averages are easy in SQL (COUNT, AVG), but SQLite has no PERCENTILE
    function for p95, and bucketing timestamps in SQL is hard to read. One query that
    fetches three small columns, then a loop in Python, is clear and fast enough here:
    30 days of checks every 30 s is ~86,000 rows, which Python handles in well under a
    second. A bigger system would pre-aggregate (e.g. an hourly summary table).
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# Candidate bucket sizes in seconds: 1 min, 5 min, 15 min, 30 min, 1 h, 2 h, 6 h, 12 h, 1 day.
# We pick the smallest one that keeps the chart at or below MAX_BUCKETS points, so
# 24 hours -> 15-minute buckets (96), 7 days -> 2-hour buckets (84), and so on.
_NICE_BUCKET_SECONDS = (60, 300, 900, 1800, 3600, 7200, 21600, 43200, 86400)
MAX_BUCKETS = 100


@dataclass(frozen=True)
class CheckPoint:
    """The three columns of a check that the statistics need."""

    checked_at: datetime
    is_up: bool
    response_ms: int | None


@dataclass
class Bucket:
    """Aggregated checks for one slice of time: one point on the chart."""

    start: datetime
    end: datetime
    total_checks: int = 0
    down_checks: int = 0
    # Collected while filling the bucket, then summarised by avg/max below.
    response_times: list[int] = field(default_factory=list)

    @property
    def avg_response_ms(self) -> int | None:
        if not self.response_times:
            return None  # no data: the chart draws a gap here, not a zero
        return round(sum(self.response_times) / len(self.response_times))

    @property
    def max_response_ms(self) -> int | None:
        return max(self.response_times) if self.response_times else None


@dataclass
class MonitorStats:
    period_start: datetime
    period_end: datetime
    bucket_seconds: int
    total_checks: int
    up_checks: int
    uptime_percent: float | None
    avg_response_ms: int | None
    p95_response_ms: int | None
    min_response_ms: int | None
    max_response_ms: int | None
    buckets: list[Bucket]

    @property
    def down_checks(self) -> int:
        return self.total_checks - self.up_checks


def choose_bucket_seconds(window_seconds: int) -> int:
    for size in _NICE_BUCKET_SECONDS:
        if window_seconds / size <= MAX_BUCKETS:
            return size
    return _NICE_BUCKET_SECONDS[-1]


def percentile(sorted_values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile: the smallest value that `pct`% of values are <= to.

    p95 = "95% of checks were at least this fast". It is more honest than the average,
    which a few very slow responses can hide behind many fast ones (or vice versa).
    `sorted_values` must already be sorted ascending.
    """
    if not sorted_values:
        return None
    rank = math.ceil(pct / 100 * len(sorted_values))  # 1-based rank
    return sorted_values[max(rank, 1) - 1]


def compute_stats(points: list[CheckPoint], period_end: datetime, hours: int) -> MonitorStats:
    """Summarise the checks that fall within the `hours` before `period_end`."""
    period_start = period_end - timedelta(hours=hours)
    bucket_seconds = choose_bucket_seconds(hours * 3600)

    # Align buckets to round clock times (e.g. 14:00, 14:15, 14:30 ...) instead of to
    # "now". Otherwise every refresh would shift all bucket edges by a few seconds and
    # the chart would wobble.
    epoch_start = int(period_start.timestamp())
    first_bucket_start = epoch_start - epoch_start % bucket_seconds
    buckets: list[Bucket] = []
    t = first_bucket_start
    while t < period_end.timestamp():
        start = datetime.fromtimestamp(t, UTC)
        buckets.append(Bucket(start=start, end=start + timedelta(seconds=bucket_seconds)))
        t += bucket_seconds

    total = up = 0
    response_times: list[int] = []
    for point in points:
        if not (period_start <= point.checked_at <= period_end):
            continue
        total += 1
        if point.is_up:
            up += 1
        if point.response_ms is not None:
            response_times.append(point.response_ms)

        # Which bucket? Integer division of "seconds since the first bucket".
        index = int(point.checked_at.timestamp() - first_bucket_start) // bucket_seconds
        bucket = buckets[min(index, len(buckets) - 1)]
        bucket.total_checks += 1
        if not point.is_up:
            bucket.down_checks += 1
        if point.response_ms is not None:
            bucket.response_times.append(point.response_ms)

    response_times.sort()
    return MonitorStats(
        period_start=period_start,
        period_end=period_end,
        bucket_seconds=bucket_seconds,
        total_checks=total,
        up_checks=up,
        # None, not 0 or 100, when there is no data: "unknown" is different from "all down".
        uptime_percent=round(up / total * 100, 2) if total else None,
        avg_response_ms=round(sum(response_times) / len(response_times)) if response_times else None,
        p95_response_ms=percentile(response_times, 95),
        min_response_ms=response_times[0] if response_times else None,
        max_response_ms=response_times[-1] if response_times else None,
        buckets=buckets,
    )
