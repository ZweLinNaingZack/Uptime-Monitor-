"""FastAPI application entry point.

Run it with:  uvicorn app.main:app --reload --port 8000
("app.main" = the module app/main.py, ":app" = the variable named `app` inside it.)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import monitors
from app.scheduler import schedule_all_active_monitors, scheduler
from app.schemas import HealthOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Code before `yield` runs once at startup, code after it once at shutdown."""
    # Create tables that don't exist yet. Fine for a learning project; real projects use
    # migrations (Alembic) so they can also *change* existing tables safely.
    Base.metadata.create_all(engine)

    # start() must happen inside a running event loop: AsyncIOScheduler attaches itself
    # to the loop that is running when it starts. The lifespan is the first place where
    # uvicorn's loop is running, which is why we don't start it at import time.
    scheduler.start()
    count = schedule_all_active_monitors()
    logger.info("Scheduler started with %d active monitor(s)", count)

    yield  # the app serves requests while we're paused here

    # wait=False: don't block shutdown waiting for in-flight checks to finish.
    scheduler.shutdown(wait=False)


app = FastAPI(title="Uptime Monitor API", version="0.1.0", lifespan=lifespan)

# CORS: browsers block JavaScript on http://localhost:3000 from reading responses from
# http://localhost:8000 (a different "origin") unless this server explicitly allows it.
# Note CORS protects *browsers' users*; it is not authentication. curl ignores it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(monitors.router)


@app.get("/health", response_model=HealthOut, tags=["health"])
def health() -> HealthOut:
    return HealthOut(status="ok")
