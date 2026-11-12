"""When an alert fires: the pure decision, the message, and the per-monitor state."""

from datetime import UTC, datetime

import pytest

from app.alerts import MAX_MESSAGE_LENGTH, AlertKind, build_message, decide_alert
from app.models import Monitor
from app.services import _update_alert_state

from .conftest import down, up

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("previous", "is_up", "failures", "threshold", "expected"),
    [
        (None, True, 0, 2, None),
        ("up", True, 0, 2, None),
        ("down", True, 0, 2, AlertKind.RECOVERED),
        ("up", False, 1, 2, None),  # one blip
        ("up", False, 2, 2, AlertKind.DOWN),
        (None, False, 2, 2, AlertKind.DOWN),  # a new monitor that never worked
        ("down", False, 9, 2, None),  # you already know
        (None, False, 1, 1, AlertKind.DOWN),  # threshold 1 alerts at once
    ],
)
def test_decide_alert(previous, is_up, failures, threshold, expected):
    assert decide_alert(previous, is_up, failures, threshold) is expected


def test_message_contents():
    message = build_message(AlertKind.DOWN, "Shop", "https://shop.example", NOW, error="HTTP 503")
    assert message.splitlines() == [
        "🔴 DOWN: Shop",
        "https://shop.example",
        "Reason: HTTP 503",
        "2026-01-02 03:04:05 UTC",
    ]
    assert "Response time: 87 ms" in build_message(AlertKind.RECOVERED, "Shop", "u", NOW, response_ms=87)


def test_long_message_is_cut_to_fit_discord():
    message = build_message(AlertKind.DOWN, "x" * 5000, "u", NOW)
    assert len(message) == MAX_MESSAGE_LENGTH
    assert message.endswith("…")


def _monitor(**kw) -> Monitor:
    defaults = dict(id=1, name="m", url="https://e.example", is_active=True, in_maintenance=False,
                    alert_state="up", consecutive_failures=0)
    return Monitor(**(defaults | kw))


def test_two_failures_in_a_row_send_one_down_then_one_recovered():
    monitor = _monitor()
    assert _update_alert_state(monitor, down(), NOW) is None
    event = _update_alert_state(monitor, down(), NOW)
    assert event is not None and event.kind == "down"
    assert _update_alert_state(monitor, down(), NOW) is None
    event = _update_alert_state(monitor, up(), NOW)
    assert event is not None and event.kind == "recovered"
    assert (monitor.alert_state, monitor.consecutive_failures) == ("up", 0)


def test_a_success_in_between_restarts_the_count():
    monitor = _monitor()
    _update_alert_state(monitor, down(), NOW)
    _update_alert_state(monitor, up(), NOW)
    assert _update_alert_state(monitor, down(), NOW) is None
    assert monitor.alert_state == "up"


@pytest.mark.parametrize("flags", [{"is_active": False}, {"in_maintenance": True}])
def test_paused_or_maintenance_changes_nothing(flags):
    monitor = _monitor(consecutive_failures=1, **flags)
    assert _update_alert_state(monitor, down(), NOW) is None
    assert (monitor.alert_state, monitor.consecutive_failures) == ("up", 1)
