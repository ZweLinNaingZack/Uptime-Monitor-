"""FastAPI application entry point.

Run it with:  uvicorn app.main:app --reload --port 8000
("app.main" = the module app/main.py, ":app" = the variable named `app` inside it.)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts import configured_channels, drain_alerts, resume_pending_alerts
from app.auth import NO_PASSWORD_MESSAGE, require_login
from app.config import settings
from app.database import run_migrations
from app.rate_limit import RateLimit
from app.routers import alerts, auth, monitors
from app.scheduler import schedule_all_active_monitors, schedule_housekeeping, scheduler
from app.schemas import HealthOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# SECURITY: at INFO level httpx logs every request's full URL. Our alert URLs contain
# secrets (the Discord webhook and the Telegram bot token), so they must never reach a log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Code before `yield` runs once at startup, code after it once at shutdown."""
    run_migrations()

    # start() must happen inside a running event loop: AsyncIOScheduler attaches itself
    # to the loop that is running when it starts. The lifespan is the first place where
    # uvicorn's loop is running, which is why we don't start it at import time.
    scheduler.start()
    count = schedule_all_active_monitors()
    schedule_housekeeping()
    logger.info("Scheduler started with %d active monitor(s)", count)
    logger.info("Alert channels configured: %s", ", ".join(configured_channels()) or "none")
    if not settings.admin_password:
        logger.warning("The API is locked: %s", NO_PASSWORD_MESSAGE)
    resumed = resume_pending_alerts()
    if resumed:
        logger.info("Resuming %d undelivered alert(s)", resumed)

    yield  # the app serves requests while we're paused here

    # wait=False: don't block shutdown waiting for in-flight checks to finish.
    scheduler.shutdown(wait=False)
    await drain_alerts()


app = FastAPI(title="Uptime Monitor API", version="0.1.0", lifespan=lifespan)

# CORS: browsers block JavaScript on http://localhost:3000 from reading responses from
# http://localhost:8000 (a different "origin") unless this server explicitly allows it.
# Note CORS protects *browsers' users*; it is not authentication. curl ignores it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Lets the browser send the login cookie on these requests, and read the responses.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

# Every route on these routers needs a login, set in one place so that a new endpoint can't
# forget it. The rate limit goes first, so it also counts requests with no valid login.
_api_limit = RateLimit(limit=300, window_seconds=60)
_protected = [Depends(_api_limit), Depends(require_login)]

app.include_router(auth.router)
app.include_router(monitors.router, dependencies=_protected)
app.include_router(alerts.router, dependencies=_protected)


@app.get("/health", response_model=HealthOut, tags=["health"])
def health() -> HealthOut:
    return HealthOut(status="ok")
