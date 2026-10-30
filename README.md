# Uptime Monitor

A small self-hosted uptime monitor, built as a learning project. You add a URL; the
backend checks it on a schedule and records each result; the dashboard shows whether
each URL is up or down, its response time, HTTP status and when it was last checked.

The code is written to be **read**: it favours clear, commented, idiomatic code over
clever code. The comments explain the "why" behind things that confuse beginners
(server vs client components, async Python, SSRF, hydration, ...).

| Part     | Stack                                                                                  |
| -------- | -------------------------------------------------------------------------------------- |
| Frontend | Next.js 16 (App Router, Cache Components), React 19, TypeScript (strict), Tailwind CSS 4 |
| Backend  | Python 3.11+, FastAPI, SQLAlchemy 2, SQLite, httpx, APScheduler 3, Pydantic v2           |

**Status:** Phase 1 (add/delete monitors, "Check now", latest result) and Phase 2
(scheduler, stored history, auto-refreshing dashboard) are done. See the [roadmap](#roadmap).

---

## Running it

You need **Python 3.11+** and **Node.js 20+**. Run the backend and frontend in two terminals.

### 1. Backend (http://localhost:8000)

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

> If PowerShell refuses to run `Activate.ps1`, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `cmd` and
> `.venv\Scripts\activate.bat`.

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for FastAPI's interactive API docs (generated from the code).

### 2. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

### Monitoring something on your own machine

By default the backend **refuses** private and loopback addresses such as
`http://localhost:5173` (see [Security](#security-notes)). For local experiments, set
`ALLOW_PRIVATE_URLS=1` in `backend/.env` and restart uvicorn. Never do this on a server
that other people can reach.

A quick local target to experiment with: `python -m http.server 8001` in any folder, then
add `http://127.0.0.1:8001/` (up) and `http://127.0.0.1:8001/nope` (404, down).

### Configuration

| Variable              | Where              | Default                 | Meaning                                         |
| --------------------- | ------------------ | ----------------------- | ----------------------------------------------- |
| `DATABASE_URL`        | `backend/.env`     | `sqlite:///./uptime.db` | SQLAlchemy URL; relative to where uvicorn runs  |
| `CORS_ORIGINS`        | `backend/.env`     | `http://localhost:3000` | Comma-separated browser origins allowed to call the API |
| `ALLOW_PRIVATE_URLS`  | `backend/.env`     | `0`                     | `1` disables SSRF protection (local dev only)   |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | `http://localhost:8000` | Backend URL, used by the server and the browser |

### Checks before committing

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

---

## Project structure

```
Uptime/
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py          FastAPI app: lifespan (create tables, start scheduler), CORS, routes
│       ├── config.py        Settings read from environment variables / .env
│       ├── database.py      Engine, sessions, PRAGMA foreign_keys, UTC datetime column type
│       ├── models.py        SQLAlchemy ORM models: Monitor, Check
│       ├── schemas.py       Pydantic models = the JSON API contract (camelCase aliases)
│       ├── url_safety.py    SSRF protection: only public IPs may be fetched
│       ├── checker.py       perform_check(url): one timed HTTP GET -> CheckResult
│       ├── services.py      run_check_for_monitor(): checker + database, used by API and scheduler
│       ├── scheduler.py     APScheduler: one job per active monitor
│       └── routers/
│           └── monitors.py  The /monitors endpoints
└── frontend/
    ├── next.config.ts       cacheComponents + partialPrefetching enabled
    ├── app/
    │   ├── layout.tsx       Root layout (header), Server Component
    │   ├── page.tsx         Dashboard, Server Component; fetches inside <Suspense>
    │   └── monitors/new/
    │       └── page.tsx     "Add monitor" page (static)
    ├── components/
    │   ├── MonitorList.tsx          Client Component: owns the list, polls, handles actions
    │   ├── MonitorCard.tsx          Presentational: one monitor's status and buttons
    │   ├── MonitorListSkeleton.tsx  Loading placeholder (Suspense fallback)
    │   └── AddMonitorForm.tsx       Client Component: the form
    ├── lib/
    │   ├── api.ts           Every fetch to the backend, ApiError, FastAPI error parsing
    │   ├── status.ts        Pure helpers: status, "12s ago", "every 5 minutes"
    │   └── useNow.ts        Ticking clock hook that avoids hydration mismatches
    └── types/
        └── index.ts         TypeScript mirror of backend/app/schemas.py
```

### Data model

```
monitors                                   checks
─────────────────────────────              ──────────────────────────────────────
id               INTEGER PK                id           INTEGER PK
name             VARCHAR(100)              monitor_id   INTEGER FK -> monitors.id ON DELETE CASCADE
url              VARCHAR(2048)             status_code  INTEGER NULL
interval_seconds INTEGER (30..86400)       response_ms  INTEGER NULL
is_active        BOOLEAN                   is_up        BOOLEAN
created_at       DATETIME (UTC)            error        TEXT NULL
                                           checked_at   DATETIME (UTC)
                                           INDEX (monitor_id, checked_at)
```

Timestamps are stored in UTC, sent as ISO strings ending in `Z`, and formatted in the
browser in the user's timezone.

---

## API

JSON uses camelCase (`intervalSeconds`); the Python code uses snake_case (`interval_seconds`).
A Pydantic `alias_generator` translates between them.

| Method   | Path                              | Body / query                                  | Response                                     |
| -------- | --------------------------------- | --------------------------------------------- | -------------------------------------------- |
| `GET`    | `/health`                         |                                               | `200 {"status": "ok"}`                       |
| `GET`    | `/monitors`                       |                                               | `200` list of monitors, each with `latestCheck` |
| `POST`   | `/monitors`                       | `{"name", "url", "intervalSeconds"?}`         | `201` monitor (`latestCheck: null`); first check starts immediately. `400` unsafe URL, `422` invalid input |
| `PATCH`  | `/monitors/{id}`                  | `{"isActive": false}` pauses, `true` resumes  | `200` monitor; resuming checks immediately   |
| `DELETE` | `/monitors/{id}`                  |                                               | `204`; its checks are deleted by the database |
| `POST`   | `/monitors/{id}/check`            |                                               | `200` the new check ("Check now")           |
| `GET`    | `/monitors/{id}/checks`           | `?limit=100` (1 to 1000)                      | `200` checks, newest first                  |

Example monitor:

```json
{
  "id": 1,
  "name": "Example",
  "url": "https://example.com/",
  "intervalSeconds": 60,
  "isActive": true,
  "createdAt": "2026-10-29T16:03:59.662960Z",
  "latestCheck": {
    "id": 7, "monitorId": 1, "statusCode": 200, "responseMs": 98,
    "isUp": true, "error": null, "checkedAt": "2026-10-29T16:04:02.181854Z"
  }
}
```

Errors follow FastAPI's two shapes, both handled in `frontend/lib/api.ts`:
`{"detail": "Monitor not found."}` and, for validation (422),
`{"detail": [{"loc": ["body", "url"], "msg": "...", "type": "..."}]}`.

**Up or down?** 2xx and 3xx responses are *up*; 4xx, 5xx, timeouts (10 s), refused
connections, DNS failures and blocked URLs are *down*, with a readable `error`. Redirects
are not followed (a 3xx already proves the server is alive, and following it could lead to
a private address).

---

## How to read this code

Follow one request all the way through. **The user clicks "Check now" on a monitor card.**

1. **The button** is in `frontend/components/MonitorCard.tsx`. MonitorCard is
   *presentational*: it calls the `onCheckNow` prop and knows nothing else.

2. **The handler** is `handleCheckNow` in `frontend/components/MonitorList.tsx`, a
   Client Component (`"use client"`). It marks the monitor busy (buttons disabled) via
   `runAction`, then calls `checkMonitorNow(id)`.

3. **The HTTP call** happens in `frontend/lib/api.ts`. `request()` builds the URL from
   `NEXT_PUBLIC_API_URL`, calls `fetch` with a timeout, and turns network failures and
   non-2xx responses into an `ApiError`.

4. **The browser sends `POST http://localhost:8000/monitors/1/check`.** Because the page
   is on a different origin (port 3000), the browser checks the backend's CORS headers,
   configured in `backend/app/main.py`.

5. **FastAPI routes it** to `check_now` in `backend/app/routers/monitors.py`. The
   `DbSession` dependency (`get_db` in `database.py`) opens a SQLAlchemy session. The
   endpoint returns 404 if the monitor doesn't exist, then **closes the session** before
   the slow part.

6. **`run_check_for_monitor`** in `backend/app/services.py` does three steps: read the
   URL (short session), check it with **no session open**, then save the result in a
   fresh session. If the monitor was deleted meanwhile, it discards the result, and the
   foreign key constraint backs this up.

7. **`perform_check`** in `backend/app/checker.py` first calls `assert_url_is_safe`
   (`url_safety.py`), which resolves DNS in a thread (`asyncio.to_thread`) and rejects
   private IPs. It then sends the GET with `httpx.AsyncClient.stream` (headers only, no
   body), with a 10 s overall deadline, and returns a `CheckResult`.

8. **The row is inserted** into `checks` (`models.py`). The `UTCDateTime` column type
   stores UTC; `PRAGMA foreign_keys=ON` (set for every connection) makes the database
   enforce `monitor_id`.

9. **The response is serialized** by the `CheckOut` schema (`schemas.py`): snake_case
   attributes become camelCase JSON, and datetimes become `...Z` strings.

10. **Back in the browser**, `handleCheckNow` puts the new check into that monitor's
    `latestCheck` with `setMonitors(prev => ...)`. React re-renders the card: badge,
    response time, status, and "Last check: just now", which keeps ticking thanks to
    `useNow()`.

Then follow the two other paths:

- **First page load:** `frontend/app/page.tsx` (Server Component) renders the heading
  immediately, and `<Suspense>` streams in `MonitorListLoader`, which awaits
  `getMonitors()` *on the Next.js server*, then hands the list to `MonitorList` as props.
- **Scheduled checks:** `backend/app/main.py` `lifespan` starts the scheduler and calls
  `schedule_all_active_monitors()`. Every interval, APScheduler runs `_scheduled_check`
  in `scheduler.py`, which calls the same `run_check_for_monitor`. The dashboard picks up
  new results through its 10-second poll in `MonitorList`.

### Questions to think about while reading

1. `page.tsx` is a Server Component and `MonitorList.tsx` is a Client Component. What
   would break if you moved the `getMonitors()` call into `MonitorList` and deleted the
   one in `page.tsx`? What would the user see first?
2. Why does `MonitorList` re-fetch in an effect when the server already sent the list?
   (Hint: read the comment about `<Activity>`. Try removing the effect, adding a monitor,
   and going back.)
3. `useNow()` returns `null` during the server render. What error would you get if it
   returned `Date.now()` instead? Why would *formatting* a date on the server cause the
   same problem?
4. `run_check_for_monitor` closes its session before the network call. What would happen
   with 50 monitors, each taking 10 s, if it didn't?
5. Why is the SSRF check done both when a monitor is created *and* before every check?
6. Why check that *every* resolved IP is public, rather than just the first?
7. What does `max_instances=1` protect against? What does `coalesce=True` do after your
   laptop wakes from sleep?
8. Why are `list_monitors` and `list_checks` plain `def`, while `check_now` is `async def`?
9. `latest_checks_by_monitor` uses a window function. Write the naive version (one query
   per monitor) and count the queries for 100 monitors.
10. Delete a monitor while its check is in flight. Which two mechanisms stop an orphan
    `checks` row from being saved?
11. `types/index.ts` duplicates `schemas.py` by hand. How could you generate it from
    FastAPI's OpenAPI schema (`/openapi.json`) instead?
12. If you ran `uvicorn --workers 4`, how many times would each check run? How would
    you fix that?

---

## Security notes

### SSRF (Server-Side Request Forgery)

The backend fetches URLs typed in by users. Without care, a user could make the server
request `http://localhost:...`, a router at `192.168.1.1`, or the cloud metadata
service at `169.254.169.254`, which hands out cloud credentials, and learn about those
internal systems from the result. Defences (`backend/app/url_safety.py`):

- Only `http` and `https` (Pydantic `HttpUrl`, plus our own check).
- The hostname is resolved, and the URL is rejected if **any** resolved address is not
  `ipaddress.ip_address(...).is_global`: loopback (`127.0.0.0/8`, `::1`), private
  (`10/8`, `172.16/12`, `192.168/16`), link-local (`169.254/16`, `fe80::/10`),
  carrier-grade NAT, `0.0.0.0`, IPv4-mapped IPv6 (`::ffff:127.0.0.1`) and so on.
- Because the *resolved IP* is checked, tricks like `http://2130706433/` (decimal
  127.0.0.1), `http://0x7f000001/`, `http://127.1/`, or a public domain whose DNS points
  to `127.0.0.1` are blocked too.
- The check runs at creation (fast feedback, `400`) **and before every check** (DNS can
  change later).
- Redirects are not followed, so a public URL cannot bounce the checker to a private one.
- `trust_env=False` stops httpx from using a proxy from the environment, which would do
  its own DNS lookup.
- DNS lookups run in a worker thread (`asyncio.to_thread`) so they don't block the event loop.
- `ALLOW_PRIVATE_URLS=1` turns this off for local development only. It is off by default.

**Known gap: DNS rebinding.** We resolve the name, then httpx resolves it again when it
connects. A malicious DNS server can answer with a public IP the first time and
`127.0.0.1` the second. Fixing that requires connecting to the exact IP we validated
(a custom transport that pins the IP while keeping the `Host` header and TLS SNI) or
sending all checks through an egress proxy that enforces the same rule.

### Other notes

- **Input validation**: Pydantic enforces name length (1 to 100), URL format and length,
  and the interval range (30 to 86400 s); unknown fields are rejected. The database also
  has a CHECK constraint on the interval.
- **CORS** allows only `CORS_ORIGINS` (default `http://localhost:3000`). CORS protects
  browser users, but it is **not** authentication: anyone who can reach port 8000 can call
  the API with curl. There is no auth yet, so keep the backend on localhost.
- **Response bodies are never downloaded** (`client.stream`), so a huge file can't
  exhaust memory, and a 10 s overall deadline bounds each check.
- Links to monitored URLs open with `rel="noreferrer"`.

---

## Roadmap

Built:

- [x] **Phase 1**: add/delete monitors, "Check now", latest result per monitor
- [x] **Phase 2**: APScheduler job per monitor, stored check history, dashboard polling every 10 s

Next (not built yet):

- [ ] **Phase 3: Stats and detail page**: `/monitors/[id]` with uptime %, average/p95
      response time, a response-time chart and a history table (the
      `GET /monitors/{id}/checks` endpoint already exists)
- [ ] **Phase 4: Alerts**: Discord/Telegram notifications when a monitor changes state
      (up to down, down to up), plus a "maintenance" state that suppresses alerts
- [ ] **Phase 5: Hardening**: rate limiting, authentication, close the DNS-rebinding gap
      (IP pinning), Alembic migrations, data retention (prune old checks)
- [ ] **Phase 6: Shipping**: Docker Compose, automated tests (pytest + a frontend test
      runner), CI running lint, type checks, tests and build
