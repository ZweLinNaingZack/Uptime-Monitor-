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

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, PlainSerializer, StringConstraints
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
    is_active: bool


# ---------- Output ----------


class CheckOut(CamelModel):
    id: int
    monitor_id: int
    status_code: int | None
    response_ms: int | None
    is_up: bool
    error: str | None
    checked_at: UtcDatetime


class MonitorOut(CamelModel):
    id: int
    name: str
    url: str
    interval_seconds: int
    is_active: bool
    created_at: UtcDatetime
    latest_check: CheckOut | None = None


class HealthOut(CamelModel):
    status: str
