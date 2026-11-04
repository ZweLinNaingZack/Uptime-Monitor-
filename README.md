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

**Status:** Phases 1 to 4 are done: add/delete monitors and "Check now"; the scheduler,
stored history and auto-refreshing dashboard; a detail page per monitor with uptime and
response-time stats, a chart and the check history; and Discord/Telegram alerts with a
maintenance state. See the [roadmap](#roadmap).

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
| `DISCORD_WEBHOOK_URL` | `backend/.env`     | empty                   | **Secret.** Discord webhook for alerts          |
| `TELEGRAM_BOT_TOKEN`  | `backend/.env`     | empty                   | **Secret.** Telegram bot token for alerts       |
| `TELEGRAM_CHAT_ID`    | `backend/.env`     | empty                   | Telegram chat that receives alerts              |
| `TELEGRAM_API_BASE`   | `backend/.env`     | `https://api.telegram.org` | Only if you run your own Bot API server      |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | `http://localhost:8000` | Backend URL, used by the server and the browser |

### Setting up alerts

Alerts are optional. You can set up Discord, Telegram, or both, in `backend/.env`. These
values are passwords: `.env` is git-ignored, so keep them there and never in
`.env.example`, a commit, or a screenshot.

**Discord**

1. In your server: **channel settings → Integrations → Webhooks → New Webhook**.
2. Click **Copy Webhook URL** and add it to `backend/.env`:
   `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...`

**Telegram**

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token it gives you
   into `TELEGRAM_BOT_TOKEN=`.
2. Send any message to your new bot (or add it to a group).
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser, find
   `"chat":{"id":...}`, and copy that number into `TELEGRAM_CHAT_ID=`.

**Then** restart the backend, open **Alerts** in the dashboard, and click **Send test
alert**. A failure shows the reason, for example `HTTP 401` for a wrong token.

### How alerts behave

| Situation | What happens |
| --------- | ------------ |
| Up → down | One `DOWN` message |
| Still down | Nothing more, however many checks fail |
| Down → up | One `RECOVERED` message |
| New monitor's first check | Fails: `DOWN`. Works: nothing |
| Backend restarts | No repeat alerts, because the last state is stored in the database |
| **Maintenance** on | Checks continue, alerts are silenced, results don't count towards uptime |
| Broken when maintenance ends | `DOWN` on the next check |
| Broke and was fixed during maintenance | Nothing |
| **Paused** monitor | No scheduled checks and no alerts, even from "Check now" |
| Discord or Telegram is failing | Retried up to 3 times. The outcome appears on the Alerts page |
| Server stops before sending | Sent at the next start, unless it is over an hour old |

A single failed check sends an alert straight away, so a brief network blip can produce a
`DOWN` followed by a `RECOVERED`. The roadmap has an option to wait for several failures.

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
│       ├── stats.py         compute_stats(): uptime %, avg/p95, chart buckets (pure functions)
│       ├── alerts.py        When to alert, sending to Discord/Telegram, retries, delivery
│       └── routers/
│           ├── monitors.py  The /monitors endpoints
│           └── alerts.py    The /alerts endpoints
└── frontend/
    ├── next.config.ts       cacheComponents + partialPrefetching enabled
    ├── app/
    │   ├── layout.tsx       Root layout (header), Server Component
    │   ├── page.tsx         Dashboard, Server Component; fetches inside <Suspense>
    │   ├── not-found.tsx    Shown for unknown URLs and notFound()
    │   ├── alerts/page.tsx  Alerts page: channel status, test button, history
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
    │   └── AlertsPanel.tsx          Client Component: the Alerts page's data and test button
    ├── lib/
    │   ├── api.ts           Every fetch to the backend, ApiError, FastAPI error parsing
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
                                           INDEX (monitor_id, checked_at)

alert_events
──────────────────────────────────────
id           INTEGER PK
monitor_id   INTEGER FK -> monitors.id ON DELETE CASCADE
kind         "down" | "recovered"
message      TEXT
status       "pending" | "sent" | "partial" | "failed" | "no_channels"
error        TEXT NULL
created_at   DATETIME (UTC)
finished_at  DATETIME (UTC) NULL
```

**Upgrading an existing database:** just start the backend. `ensure_schema()` in
`database.py` creates missing tables and adds missing columns without touching your rows.

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
| `PATCH`  | `/monitors/{id}`                  | `{"isActive"?: bool, "inMaintenance"?: bool}`, at least one | `200` monitor; resuming checks immediately |
| `DELETE` | `/monitors/{id}`                  |                                               | `204`; its checks are deleted by the database |
| `POST`   | `/monitors/{id}/check`            |                                               | `200` the new check ("Check now")           |
| `GET`    | `/monitors/{id}`                  |                                               | `200` one monitor with `latestCheck`, or `404` |
| `GET`    | `/monitors/{id}/checks`           | `?limit=100` (1 to 1000)                      | `200` checks, newest first                  |
| `GET`    | `/monitors/{id}/stats`            | `?hours=24` (1 to 720)                        | `200` uptime %, avg/p95/min/max response time, and chart `buckets` |
| `GET`    | `/alerts`                         | `?limit=50` (1 to 500)                        | `200` alert history, newest first           |
| `GET`    | `/alerts/channels`                |                                               | `200` which channels are set up (never the secrets) |
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
26. Why do webhook URLs live in `.env` rather than in a form on the dashboard? What would
    have to exist first for that form to be safe? (Think about Phase 5, and SSRF.)
27. `run_check_for_monitor` can take the "Check now" path or the scheduler path. If both
    finish at nearly the same time, why can't they both send the same `DOWN` alert?
    (Hint: is there an `await` between reading `alert_state` and committing?)

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

### Alert secrets

A Discord webhook URL or Telegram bot token lets anyone holding it post as you, so:

- They are set only through environment variables. No API endpoint accepts or returns
  them; `GET /alerts/channels` only says whether each channel is set up.
- They stay out of logs (the `httpx` logger is limited to warnings) and out of stored
  error messages, which use only status codes and class names.
- Messages are sent as plain text with Discord mentions disabled, so a monitor named
  `@everyone` can't ping your whole server.

**If a secret leaks,** replace it: delete the webhook in Discord, or send `/revoke` to
@BotFather for a Telegram token.

**Known limit:** without a login, anyone who can reach the API can call `POST /alerts/test`
repeatedly or switch a monitor to maintenance to silence its alerts. Keep the backend on
localhost until authentication and rate limiting exist (Phase 5).

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
- [x] **Phase 3**: `/monitors/[id]` detail page with uptime %, average/p95 response time,
      a response-time chart with a status strip (24 h / 7 d / 30 d), and the check history
- [x] **Phase 4**: Discord/Telegram alerts on state changes, retries, alert history, a
      test button, and a maintenance state

Next (not built yet):

- [ ] **Phase 5: Hardening**: rate limiting, authentication, close the DNS-rebinding gap
      (IP pinning), Alembic migrations, data retention (prune old checks), configuring
      alert channels from the dashboard (safe only once a login exists), and waiting for
      several failed checks before alerting
- [ ] **Phase 6: Shipping**: Docker Compose, automated tests (pytest + a frontend test
      runner), CI running lint, type checks, tests and build
