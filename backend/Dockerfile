# The backend as a container image. Built by docker-compose.yml in the project root.
FROM python:3.13-slim

# Don't write .pyc files into the image, and print logs immediately instead of buffering
# them, so `docker compose logs` shows them as they happen.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, the code after. Docker caches each step, so editing the code reuses
# the slow "pip install" layer as long as requirements.txt hasn't changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Run as an ordinary user, not root: if someone ever broke into the app, they'd have far
# fewer permissions. /data holds the SQLite database, on a volume that outlives the container.
RUN useradd --create-home --uid 10001 uptime \
    && mkdir /data \
    && chown uptime /data
USER uptime
ENV DATABASE_URL=sqlite:////data/uptime.db

EXPOSE 8000
# Lets Docker (and the frontend's depends_on) know when the API is really ready.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# 0.0.0.0, not 127.0.0.1: inside a container, 127.0.0.1 is unreachable from outside it.
# No --reload, and exactly one worker: each worker would start its own scheduler.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
