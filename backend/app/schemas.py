"""Pydantic schemas: the shape of JSON going in and out of the API.

Why separate from the ORM models in models.py?
- The API contract and the database layout change for different reasons.
- Input schemas validate untrusted data (lengths, ranges, URL format) before it reaches
  the database. Output schemas decide exactly which fields are exposed.

Naming: Python uses snake_case, JavaScript uses camelCase. `alias_generator=to_camel`
makes `interval_seconds` appear as `intervalSeconds` in JSON, so neither side has to
write code in the other language's style. The TypeScript mirror is frontend/types/index.ts.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PlainSerializer,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.models import DEFAULT_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS


def _to_utc_iso(value: datetime) -> str:
    # 2026-10-29T12:00:00.123456+00:00  ->  2026-10-29T12:00:00.123456Z
    # The trailing "Z" ("Zulu" = UTC) is what JavaScript's Date parser expects. The
    # browser then formats the time in the *user's* timezone.
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso, return_type=str)]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        # Also accept snake_case names on input (handy in tests and Python callers).
        populate_by_name=True,
        # Allow `CheckOut.model_validate(orm_check)`: read attributes, not dict keys.
        from_attributes=True,
        # Reject unknown fields such as {"isActiv": true} instead of silently ignoring them.
        extra="forbid",
    )


# ---------- Input ----------

MonitorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class MonitorCreate(CamelModel):
    name: MonitorName
    # HttpUrl only accepts http/https URLs with a host, and caps the length at 2083 chars.
    # It does NOT protect against SSRF: http://127.0.0.1 is a perfectly valid URL.
    # That check is in url_safety.py because it needs a DNS lookup.
    url: HttpUrl
    interval_seconds: int = Field(
        default=DEFAULT_INTERVAL_SECONDS, ge=MIN_INTERVAL_SECONDS, le=MAX_INTERVAL_SECONDS
    )


class MonitorUpdate(CamelModel):
    """PATCH body: send only what you want to change, but send at least one field."""

    is_active: bool | None = None
    in_maintenance: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "MonitorUpdate":
        if self.is_active is None and self.in_maintenance is None:
            raise ValueError("Provide isActive or inMaintenance.")
        return self


# ---------- Output ----------


class CheckOut(CamelModel):
    id: int
    monitor_id: int
    status_code: int | None
    response_ms: int | None
    is_up: bool
    error: str | None
    checked_at: UtcDatetime
    during_maintenance: bool


class MonitorOut(CamelModel):
    id: int
    name: str
    url: str
    interval_seconds: int
    is_active: bool
    in_maintenance: bool
    created_at: UtcDatetime
    latest_check: CheckOut | None = None


class StatsBucketOut(CamelModel):
    """One point on the response-time chart: all checks between `start` and `end`."""

    start: UtcDatetime
    end: UtcDatetime
    total_checks: int
    down_checks: int
    avg_response_ms: int | None  # None = no response in this slice (chart shows a gap)
    max_response_ms: int | None


class MonitorStatsOut(CamelModel):
    monitor_id: int
    period_hours: int
    period_start: UtcDatetime
    period_end: UtcDatetime
    bucket_seconds: int
    total_checks: int
    up_checks: int
    down_checks: int
    # The following are None when the period has no (responding) checks yet.
    uptime_percent: float | None
    avg_response_ms: int | None
    p95_response_ms: int | None
    min_response_ms: int | None
    max_response_ms: int | None
    buckets: list[StatsBucketOut]


class AlertEventOut(CamelModel):
    id: int
    monitor_id: int
    monitor_name: str
    kind: str
    message: str
    status: str
    error: str | None
    created_at: UtcDatetime
    finished_at: UtcDatetime | None


class AlertChannelOut(CamelModel):
    """Whether a channel is set up. Deliberately has no field for the secret itself."""

    name: str
    configured: bool


class AlertTestResultOut(CamelModel):
    channel: str
    ok: bool
    error: str | None


class HealthOut(CamelModel):
    status: str
