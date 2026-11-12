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

**Status:** All six phases are done: add/delete monitors and "Check now"; the scheduler,
stored history and auto-refreshing dashboard; a detail page per monitor with uptime and
response-time stats, a chart and the check history; Discord/Telegram alerts with a
maintenance state; hardening (a login, rate limits, database migrations, cleanup of old
data); and shipping: Docker Compose, automated tests and CI. See the [roadmap](#roadmap).

---

## Running it

There are two ways: with Docker (one command, nothing else to install), or directly on your
machine (better while you're changing the code).

### With Docker

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
with Compose.

1. Create `backend/.env` from `backend/.env.example` and set `ADMIN_PASSWORD` (and your
   alert channels, if any). `DATABASE_URL` and `CORS_ORIGINS` in that file are ignored here.
2. From the project folder, run:

   ```bash
   docker compose up --build
   ```

3. Open http://localhost:3000 and log in.

The database lives in a Docker volume called `uptime-data`, so it survives restarts and
rebuilds. `docker compose down` stops everything and keeps the data; `docker compose down
--volumes` deletes the data too. Both ports only accept connections from your own computer.

Inside Docker, `localhost` means the container itself, so a monitor for
`http://localhost:5173` checks the container, not your computer. Use
`http://host.docker.internal:5173` (with `ALLOW_PRIVATE_URLS=1`) to reach your computer.

### Directly on your machine

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

**Before you start it,** open `backend/.env` and choose a password:

```
ADMIN_PASSWORD=choose-a-long-password
```

Until this is set, the API stays locked and the login page tells you so. Restart the backend
after changing `.env`.

Open http://localhost:8000/docs for FastAPI's interactive API docs (generated from the code).

### 2. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and log in with your password. Use `localhost`, not `127.0.0.1`:
browsers treat them as different sites, so the login cookie and CORS only work on the one
named in `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL`.

**Forgot the password?** Change `ADMIN_PASSWORD` in `.env` and restart. **Typed it wrong five
times?** Logging in is blocked for up to five minutes, or until the backend restarts.

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
| `ADMIN_PASSWORD`      | `backend/.env`     | empty                   | **Secret, required.** The dashboard password. Empty keeps the API locked |
| `COOKIE_SECURE`       | `backend/.env`     | `0`                     | `1` sends the login cookie over HTTPS only. Turn on when you deploy with HTTPS |
| `ALERT_FAILURE_THRESHOLD` | `backend/.env` | `2`                     | Failed checks in a row before a `DOWN` alert    |
| `RETENTION_DAYS`      | `backend/.env`     | `90`                    | Delete checks and finished alerts older than this. `0` keeps them forever |
| `DISCORD_WEBHOOK_URL` | `backend/.env`     | empty                   | **Secret.** Discord webhook for alerts. The Alerts page can override it |
| `TELEGRAM_BOT_TOKEN`  | `backend/.env`     | empty                   | **Secret.** Telegram bot token for alerts. The Alerts page can override it |
| `TELEGRAM_CHAT_ID`    | `backend/.env`     | empty                   | Telegram chat that receives alerts              |
| `TELEGRAM_API_BASE`   | `backend/.env`     | `https://api.telegram.org` | Only if you run your own Bot API server      |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | `http://localhost:8000` | Backend URL for the browser (and the server, unless the next row is set). Built into the JavaScript, so changing it needs a rebuild |
| `API_INTERNAL_URL`    | frontend environment | empty                | Backend URL for the Next.js server only. Docker Compose sets it to `http://backend:8000` |

### Setting up alerts

Alerts are optional. You can set up Discord, Telegram, or both, in either of two places:

- **The Alerts page in the dashboard.** It takes effect immediately, and overrides `.env`.
  The value is saved in `uptime.db`.
- **`backend/.env`.** Restart the backend after changing it.

These values are passwords: keep them out of `.env.example`, commits and screenshots.

**Discord**

1. In your server: **channel settings → Integrations → Webhooks → New Webhook**.
2. Click **Copy Webhook URL**. On the Alerts page, paste it into **Webhook URL**. In `.env`,
   use `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

**Telegram**

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token it gives you.
   In `.env`, that's `TELEGRAM_BOT_TOKEN=`.
2. Send any message to your new bot (or add it to a group).
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser and find
   `"chat":{"id":...}`. That number is your chat ID. In `.env`, that's `TELEGRAM_CHAT_ID=`.

**Then** open **Alerts** in the dashboard and click **Send test alert**. A failure shows the
reason, for example `HTTP 401` for a wrong token.

### How alerts behave

| Situation | What happens |
| --------- | ------------ |
| One failed check, then working again | Nothing: it could be a network blip |
| 2 failed checks in a row (`ALERT_FAILURE_THRESHOLD`) | One `DOWN` message |
| Still down | Nothing more, however many checks fail |
| Down → up | One `RECOVERED` message |
| New monitor | The same rules. Working from the start: nothing |
| Backend restarts | No repeat alerts, because the last state is stored in the database |
| **Maintenance** on | Checks continue, alerts are silenced, results don't count towards uptime |
| Broken when maintenance ends | `DOWN` on the next check |
| Broke and was fixed during maintenance | Nothing |
| **Paused** monitor | No scheduled checks and no alerts, even from "Check now" |
| Discord or Telegram is failing | Retried up to 3 times. The outcome appears on the Alerts page |
| Server stops before sending | Sent at the next start, unless it is over an hour old |

Waiting has a cost: at a 5-minute interval, a `DOWN` alert arrives up to 10 minutes after the
site breaks. Set `ALERT_FAILURE_THRESHOLD=1` if you'd rather hear immediately and put up with
the odd false alarm. Pausing a monitor or switching maintenance resets the count.

### Tests and checks

GitHub runs all of these on every push (see `.github/workflows/ci.yml`). Run them yourself
before committing, so a problem shows up on your machine first.

Backend, from `backend/` with the virtual environment active (install the test tools once
with `pip install -r requirements-dev.txt`):

```bash
python -m pytest
```

Frontend, from `frontend/`:

```bash
npm run lint
```

```bash
npm test
```

```bash
npm run build
```

```bash
npx tsc --noEmit
```

`npm run test:watch` reruns the frontend tests every time you save a file.

The tests never use the network or your real settings: `backend/tests/conftest.py` sets its
own password and an empty database, and replaces DNS, website checks and alert sending with
fakes. So they're fast, give the same result every time, and can't message your channels.

---

## Project structure

```
Uptime/
├── docker-compose.yml       Runs backend + frontend together: `docker compose up --build`
├── .github/workflows/ci.yml Tests, lint, type check, build and Docker on every push
├── backend/
│   ├── requirements.txt     What the app needs
│   ├── requirements-dev.txt ...plus the test tools
│   ├── pyproject.toml       pytest settings
│   ├── Dockerfile           The backend image
│   ├── .env.example
│   ├── alembic.ini          Settings for the `alembic` command
│   ├── migrations/          Database changes, one numbered file each (versions/)
│   ├── tests/               pytest: conftest.py (fakes and fixtures) and one file per area
│   └── app/
│       ├── main.py          FastAPI app: lifespan (migrate, start scheduler), CORS, routes
│       ├── config.py        Settings read from environment variables / .env
│       ├── database.py      Engine, sessions, migrations, PRAGMA foreign_keys, UTC datetime type
│       ├── models.py        SQLAlchemy ORM models: Monitor, Check, AlertEvent, AuthSession, ...
│       ├── schemas.py       Pydantic models = the JSON API contract (camelCase aliases)
│       ├── url_safety.py    SSRF protection: only public IPs may be fetched
│       ├── checker.py       perform_check(url): one timed HTTP GET to an approved IP -> CheckResult
│       ├── services.py      run_check_for_monitor(): checker + database, used by API and scheduler
│       ├── scheduler.py     APScheduler: one job per active monitor, plus daily housekeeping
│       ├── retention.py     prune_old_data(): deletes old checks, alerts and expired logins
│       ├── stats.py         compute_stats(): uptime %, avg/p95, chart buckets (pure functions)
│       ├── alerts.py        When to alert, sending to Discord/Telegram, retries, delivery
│       ├── auth.py          Password check, session cookie, require_login dependency
│       ├── rate_limit.py    Sliding-window limit per IP address
│       └── routers/
│           ├── auth.py      The /auth endpoints (log in, log out)
│           ├── monitors.py  The /monitors endpoints
│           └── alerts.py    The /alerts endpoints
└── frontend/
    ├── next.config.ts       cacheComponents + partialPrefetching; standalone output in Docker
    ├── vitest.config.mts    Vitest settings
    ├── Dockerfile           The frontend image (three stages)
    ├── __tests__/           Vitest: helpers, the API client, and a component
    ├── proxy.ts             Sends visitors with no session cookie to /login
    ├── app/
    │   ├── layout.tsx       Root layout (header), Server Component
    │   ├── page.tsx         Dashboard, Server Component; fetches inside <Suspense>
    │   ├── not-found.tsx    Shown for unknown URLs and notFound()
    │   ├── login/page.tsx   Login page (static)
    │   ├── alerts/page.tsx  Alerts page: channel settings, test button, history
    │   └── monitors/
    │       ├── new/page.tsx     "Add monitor" page (static)
    │       └── [id]/page.tsx    Detail page: dynamic route, reads params inside <Suspense>
    ├── components/
    │   ├── MonitorList.tsx          Client Component: owns the list, polls, handles actions
    │   ├── MonitorCard.tsx          Presentational: one monitor's status and buttons
    │   ├── MonitorListSkeleton.tsx  Loading placeholder (Suspense fallback)
    │   ├── AddMonitorForm.tsx       Client Component: the form
    │   ├── MonitorDetail.tsx        Client Component: detail page data, period picker, actions
    │   ├── StatTiles.tsx            Presentational: uptime / avg / p95 / failed checks
    │   ├── ResponseTimeChart.tsx    Client Component: hand-drawn SVG chart with hover tooltip
    │   ├── CheckHistoryTable.tsx    Presentational: the latest 100 checks
    │   ├── AlertsPanel.tsx          Client Component: the Alerts page's data and test button
    │   ├── ChannelSettingsForm.tsx  Client Component: set up or remove one alert channel
    │   ├── LoginForm.tsx            Client Component: the password form
    │   └── HeaderNav.tsx            Client Component: header links and Log out
    ├── lib/
    │   ├── api.ts           Every fetch to the backend, ApiError, FastAPI error parsing
    │   ├── serverAuth.ts    Server only: forward the login cookie, redirect if logged out
    │   ├── monitorDetail.ts Detail-page data loading, shared by server and client
    │   ├── status.ts        Pure helpers: status, "12s ago", "457 ms", "99.95%"
    │   ├── useNow.ts        Ticking clock hook that avoids hydration mismatches
    │   └── usePolling.ts    Refresh now + every N seconds + when the tab becomes visible
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
in_maintenance   BOOLEAN                   checked_at   DATETIME (UTC)
alert_state      VARCHAR(10) NULL          during_maintenance BOOLEAN
consecutive_failures INTEGER               INDEX (monitor_id, checked_at)

alert_events                               auth_sessions
──────────────────────────────────────     ──────────────────────────────
id           INTEGER PK                    id           INTEGER PK
monitor_id   INTEGER FK -> monitors.id     token_hash   VARCHAR(64) UNIQUE
             ON DELETE CASCADE             created_at   DATETIME (UTC)
kind         "down" | "recovered"          expires_at   DATETIME (UTC)
message      TEXT
status       "pending" | "sent" | "partial" | "failed" | "no_channels"
error        TEXT NULL                     alert_channel_settings
created_at   DATETIME (UTC)                ──────────────────────────────
finished_at  DATETIME (UTC) NULL           name         "discord" | "telegram" PK
                                           secret       TEXT
                                           chat_id      VARCHAR(100) NULL
                                           updated_at   DATETIME (UTC)
```

**Upgrading an existing database:** just start the backend. It runs any new migrations at
startup, and your rows stay as they are.

**Changing the schema yourself:** edit `models.py`, then run these from `backend/` with the
virtual environment active. Read the generated file before you trust it, because Alembic
can't tell a renamed column from one dropped and one added.

```bash
alembic revision --autogenerate -m "describe the change"
```

```bash
alembic upgrade head
```

Timestamps are stored in UTC, sent as ISO strings ending in `Z`, and formatted in the
browser in the user's timezone.

---

## API

JSON uses camelCase (`intervalSeconds`); the Python code uses snake_case (`interval_seconds`).
A Pydantic `alias_generator` translates between them.

Everything except `/health` and `/auth/*` needs a login: no valid cookie gets `401`, and no
`ADMIN_PASSWORD` on the server gets `503`. Too many requests get `429` with a `Retry-After`
header.

| Method   | Path                              | Body / query                                  | Response                                     |
| -------- | --------------------------------- | --------------------------------------------- | -------------------------------------------- |
| `GET`    | `/health`                         |                                               | `200 {"status": "ok"}`                       |
| `POST`   | `/auth/login`                     | `{"password"}`                                | `204` and a session cookie. `401` wrong password |
| `POST`   | `/auth/logout`                    |                                               | `204`; that session stops working           |
| `GET`    | `/monitors`                       |                                               | `200` list of monitors, each with `latestCheck` |
| `POST`   | `/monitors`                       | `{"name", "url", "intervalSeconds"?}`         | `201` monitor (`latestCheck: null`); first check starts immediately. `400` unsafe URL, `422` invalid input |
| `PATCH`  | `/monitors/{id}`                  | `{"isActive"?: bool, "inMaintenance"?: bool}`, at least one | `200` monitor; resuming checks immediately |
| `DELETE` | `/monitors/{id}`                  |                                               | `204`; its checks are deleted by the database |
| `POST`   | `/monitors/{id}/check`            |                                               | `200` the new check ("Check now")           |
| `GET`    | `/monitors/{id}`                  |                                               | `200` one monitor with `latestCheck`, or `404` |
| `GET`    | `/monitors/{id}/checks`           | `?limit=100` (1 to 1000)                      | `200` checks, newest first                  |
| `GET`    | `/monitors/{id}/stats`            | `?hours=24` (1 to 720)                        | `200` uptime %, avg/p95/min/max response time, and chart `buckets` |
| `GET`    | `/alerts`                         | `?limit=50` (1 to 500)                        | `200` alert history, newest first           |
| `GET`    | `/alerts/channels`                |                                               | `200` which channels are set up and from where (never the secrets) |
| `PUT`    | `/alerts/channels/discord`        | `{"webhookUrl"}`                              | `200` channel list. `400` not a Discord webhook URL |
| `PUT`    | `/alerts/channels/telegram`       | `{"botToken", "chatId"}`                      | `200` channel list. `400` wrong format      |
| `DELETE` | `/alerts/channels/{name}`         |                                               | `200` channel list. `404` nothing saved in the dashboard |
| `POST`   | `/alerts/test`                    |                                               | `200` per-channel result. `400` if none is set up |

**Stats details.** Uptime % is up checks ÷ all checks in the period. Response-time
figures only count checks that got a response (a timeout has no response time). p95 uses
the nearest-rank method. Values are `null`, not `0`, when there is no data yet. Checks
made during maintenance are left out. The
period is split into at most 100 buckets of a "nice" size (24 h → 15 min, 7 d → 2 h,
30 d → 12 h), aligned to clock times so the chart doesn't shift on every refresh.

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
  new results through its 10-second poll (`usePolling` in `MonitorList`).
- **Detail page:** `frontend/app/monitors/[id]/page.tsx` awaits the `params` Promise
  inside `<Suspense>`, validates the id, and calls `fetchMonitorDetail` (`lib/monitorDetail.ts`),
  which fetches the monitor, stats and history in parallel. On the backend,
  `get_monitor_stats` (`routers/monitors.py`) selects three columns for the period and
  hands them to `compute_stats` (`stats.py`). In the browser, `MonitorDetail` keeps it
  fresh; switching the period changes `hours`, which recreates `refresh`, which restarts
  `usePolling` and fetches immediately.
- **An alert:** at the end of `run_check_for_monitor` (`services.py`), `_update_alert_state`
  asks `decide_alert` (`alerts.py`) whether the state changed. If it did, an `AlertEvent`
  is saved in the same commit as the check. Only after that commit does `dispatch_alert`
  start a background task, so the check doesn't wait for Discord. `_deliver` then sends
  the message with no database session open, and saves the outcome in a fresh session.

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

Phase 3:

13. `fetchMonitorDetail` lives in `lib/monitorDetail.ts`, not in `MonitorDetail.tsx`.
    What goes wrong if a Server Component imports a plain function from a
    `"use client"` file and calls it?
14. Why does the stats API return `null` instead of `0` when there are no checks? What
    would the chart and the "Uptime" tile wrongly suggest otherwise?
15. Why is p95 more useful than the average for response times? Construct 20 response
    times where the average looks fine but p95 reveals a problem.
16. `MonitorDetail` numbers each request (`latestRequest`). Click "7 days" then "30 days"
    quickly: what bug would appear without it? Why is it a `useRef`, not `useState`?
17. `StatTiles` uses `formatCount` with a fixed `"en-US"` locale instead of
    `toLocaleString()`. What would a German visitor see in the console otherwise?
18. Visit `/monitors/999` and check the HTTP status in your browser's network tab. Why is
    it 200, not 404? (Hint: streaming.)
19. The chart is hand-written SVG. Find where a millisecond value becomes a pixel
    (`y = ...`). Why does a bigger value give a *smaller* y?

Phase 4:

20. `main.py` sets the `httpx` logger to WARNING. What would appear in your server log
    without that line, and why is that dangerous for alerts specifically?
21. Why are alert errors built from status codes and class names, never `str(exc)`?
22. `AlertEvent` is saved *before* anything is sent. What could go wrong if you sent
    first and saved afterwards? What could go wrong with the order used here? (Hint:
    which failure gives a lost alert, and which gives a duplicate?)
23. While paused or in maintenance, `alert_state` isn't touched at all. Walk through "the
    site broke during maintenance and is still broken when it ends". Which line sends
    the `DOWN`?
24. Why does `dispatch_alert` keep tasks in `_delivery_tasks`? What can happen to an
    `asyncio.create_task` result that nothing refers to?
25. Why are 500 and 429 retried, but 401 isn't?
26. Phase 5 added a form for webhook URLs. Why wasn't it safe before there was a login? Why
    does `routers/alerts.py` still only accept real Discord addresses, now that there is one?
27. `run_check_for_monitor` can take the "Check now" path or the scheduler path. If both
    finish at nearly the same time, why can't they both send the same `DOWN` alert?
    (Hint: is there an `await` between reading `alert_state` and committing?)

Phase 5:

28. `_hash_token` uses plain SHA-256, yet everyone says never to store passwords that way.
    Why is it fine for this token? What would an attacker holding `uptime.db` be able to do
    if the table stored the token itself?
29. `proxy.ts` lets through any request that has a cookie with the right name, even a
    made-up one. Why isn't that a security hole? Where is the real check?
30. In `_pinned_targets`, the request goes to an IP, but HTTPS still checks the certificate
    against the hostname. Which line makes that happen? What would an attacker gain if the
    certificate were checked against the IP instead?
31. A wrong password counts towards the login limit, but a right one doesn't. How could an
    attacker lock you out if all attempts counted? Can they still lock you out from their
    own IP address?
32. What does `AlertEvent.status != "pending"` protect in `prune_old_data`?
33. Migration `0001_baseline.py` checks which tables exist before creating them. Normal
    migrations don't. What made this one different?
34. `lib/serverAuth.ts` starts with `import "server-only"`. What would happen, and when,
    if a Client Component imported it? Why is a failed build better than the alternative?

Phase 6:

35. `tests/conftest.py` sets environment variables *before* `from app...` imports. What
    would go wrong if the imports came first? (Hint: when is `settings` created?)
36. The API tests replace `schedule_monitor` with a function that only records its calls.
    What would make a test that counts checks fail "sometimes" without that?
37. Why does the frontend need both `NEXT_PUBLIC_API_URL` and `API_INTERNAL_URL` under
    Docker? Which one ends up in the JavaScript your browser downloads?
38. Each Dockerfile copies the dependency list and installs it *before* copying the code.
    What does that save each time you change one line of code and rebuild?
39. In `ci.yml`, why does `npm run build` come before `npx tsc --noEmit`?

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
- **DNS rebinding is blocked by pinning the IP.** A malicious DNS server could answer with a
  public IP when we check and `127.0.0.1` when we connect. So the checker connects to the
  exact IPs it approved and never looks the name up a second time. It still sends the real
  hostname in the `Host` header and TLS SNI, and HTTPS certificates are still checked
  against that hostname.

### Login

- **One shared password** (`ADMIN_PASSWORD`). There are no user accounts. With no password
  set, the API stays locked instead of open.
- **Session cookie**: a 256-bit random token, valid for 7 days. It is `HttpOnly` (scripts
  can't read it) and `SameSite=Lax` (other sites can't send it on their requests). The
  database stores only its hash, and logging out deletes it.
- **Foreign pages are refused**: a request that changes something gets `403` if its `Origin`
  header isn't in `CORS_ORIGINS`.
- **Rate limits per IP address**:

  | What | Limit |
  | ---- | ----- |
  | Wrong passwords | 5 per 5 minutes |
  | Test alerts | 5 per minute |
  | Channel changes | 10 per minute |
  | "Check now", adding monitors | 30 per minute each |
  | All other API requests | 300 per minute |

**Before putting this on the internet:** serve it over HTTPS and set `COOKIE_SECURE=1`, or
the password and cookie cross the network readable by anyone in between. If it runs behind
a reverse proxy, all visitors appear to share the proxy's IP address, so one person's wrong
passwords can block everyone. The limits also reset when the backend restarts.

### Alert secrets

A Discord webhook URL or Telegram bot token lets anyone holding it post as you, so:

- `.env` values stay on the server. Values entered on the Alerts page are saved as **plain
  text** in `uptime.db`, because the app has to read them back to send alerts. Protect
  that file like `.env`: it is git-ignored, and anyone who can read it can read them.
- No API endpoint returns them; `GET /alerts/channels` only says whether each channel is set
  up, and the error messages for rejected values don't repeat them.
- Saved values must match the real Discord and Telegram formats, so even someone with a
  stolen login can't make this server POST to any other address.
- They stay out of logs (the `httpx` logger is limited to warnings) and out of stored
  error messages, which use only status codes and class names.
- Messages are sent as plain text with Discord mentions disabled, so a monitor named
  `@everyone` can't ping your whole server.

**If a secret leaks,** replace it: delete the webhook in Discord, or send `/revoke` to
@BotFather for a Telegram token.

### Other notes

- **Input validation**: Pydantic enforces name length (1 to 100), URL format and length,
  and the interval range (30 to 86400 s); unknown fields are rejected. The database also
  has a CHECK constraint on the interval.
- **CORS** allows only `CORS_ORIGINS` (default `http://localhost:3000`). CORS protects
  browser users, but it is **not** authentication: curl ignores it. The login is what
  protects the API.
- **Old data is deleted** after `RETENTION_DAYS` (90 by default), once at startup and then
  daily. Alerts still waiting to be sent are kept.
- **Response bodies are never downloaded** (`client.stream`), so a huge file can't
  exhaust memory, and a 10 s overall deadline bounds each check.
- Links to monitored URLs open with `rel="noreferrer"`.

---

## Roadmap

Built:

- [x] **Phase 1**: add/delete monitors, "Check now", latest result per monitor
- [x] **Phase 2**: APScheduler job per monitor, stored check history, dashboard polling every 10 s
- [x] **Phase 3**: `/monitors/[id]` detail page with uptime %, average/p95 response time,
      a response-time chart with a status strip (24 h / 7 d / 30 d), and the check history
- [x] **Phase 4**: Discord/Telegram alerts on state changes, retries, alert history, a
      test button, and a maintenance state
- [x] **Phase 5**: a login, rate limits, IP pinning against DNS rebinding, Alembic
      migrations, deleting old data, alert channels set from the dashboard, and waiting for
      several failed checks before alerting
- [x] **Phase 6**: Docker Compose, automated tests (pytest and Vitest), and CI running
      lint, type checks, tests, the build and the Docker images

Ideas for later:

- [ ] HTTPS in the Docker setup, with a reverse proxy such as Caddy
- [ ] Browser tests (Playwright) for the full login → dashboard flow
- [ ] More checks than "does it answer": expected text in the page, or a certificate
      that's about to expire
