"""compute_stats and its helpers: pure functions, so no database or app is needed."""

from datetime import UTC, datetime, timedelta

import pytest

from app.stats import CheckPoint, choose_bucket_seconds, compute_stats, percentile

END = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(("values", "expected"), [([], None), ([5], 5), (list(range(1, 101)), 95), ([1, 2, 3], 3)])
def test_percentile_uses_nearest_rank(values, expected):
    assert percentile(values, 95) == expected


@pytest.mark.parametrize(("hours", "seconds"), [(24, 15 * 60), (24 * 7, 2 * 3600), (24 * 30, 12 * 3600)])
def test_bucket_sizes(hours, seconds):
    assert choose_bucket_seconds(hours * 3600) == seconds


def test_no_checks_means_unknown_not_zero():
    stats = compute_stats([], END, 24)
    assert stats.total_checks == 0
    assert stats.uptime_percent is None and stats.avg_response_ms is None


def test_uptime_and_response_times():
    points = [CheckPoint(END - timedelta(minutes=i), True, 100) for i in range(1, 4)]
    points.append(CheckPoint(END - timedelta(minutes=5), False, None))
    points.append(CheckPoint(END - timedelta(hours=25), False, None))  # outside the period
    stats = compute_stats(points, END, 24)
    assert (stats.total_checks, stats.up_checks, stats.down_checks) == (4, 3, 1)
    assert stats.uptime_percent == 75.0
    assert stats.avg_response_ms == 100  # the timeout has no response time to average
    assert sum(b.total_checks for b in stats.buckets) == 4


def test_buckets_are_aligned_to_clock_times():
    stats = compute_stats([], END + timedelta(seconds=37), 24)
    assert all(b.start.minute % 15 == 0 and b.start.second == 0 for b in stats.buckets)
