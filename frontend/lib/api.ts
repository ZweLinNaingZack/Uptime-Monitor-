// Every call to the backend lives in this file.
//
// Why one file? Components stay about *what* to show, and this file is about *how* to
// talk to the server: the base URL, JSON headers, and turning failures into one error
// type (ApiError). If the API changes, there is exactly one place to update.
//
// This module is imported from BOTH Server Components (app/page.tsx, which runs in
// Node.js) and Client Components (which run in the browser). The global `fetch` exists
// in both environments, so the same code works in both places.

import type { Check, Monitor, MonitorCreateInput, MonitorUpdateInput } from "@/types";

// NEXT_PUBLIC_ variables are copied ("inlined") into the browser JavaScript at build
// time. Never put a secret in one. A plain API_URL would be invisible to the browser.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

/** A failed API call. `status` is 0 when the backend could not be reached at all. */
export class ApiError extends Error {
  readonly status: number;
  /** Validation messages keyed by field name, e.g. { url: "URL scheme should be ..." }. */
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

// ---------- Parsing FastAPI error bodies ----------
//
// FastAPI sends errors in two shapes:
//   1. HTTPException:      {"detail": "Monitor not found."}
//   2. 422 validation:     {"detail": [{"loc": ["body", "url"], "msg": "...", "type": "..."}]}
// The body arrives as `unknown` (we can't trust it), so we narrow it step by step with
// type guards instead of casting to `any`.

interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  return (
    isRecord(value) &&
    typeof value.msg === "string" &&
    Array.isArray(value.loc) &&
    value.loc.every((part) => typeof part === "string" || typeof part === "number")
  );
}

function parseErrorBody(
  body: unknown,
  status: number,
): { message: string; fieldErrors: Record<string, string> } {
  const fallback = `Request failed with status ${status}.`;
  if (!isRecord(body)) return { message: fallback, fieldErrors: {} };

  const { detail } = body;
  if (typeof detail === "string") return { message: detail, fieldErrors: {} };

  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    const messages: string[] = [];
    for (const issue of detail.filter(isValidationIssue)) {
      // loc looks like ["body", "url"]; the last part is the field name.
      const field = String(issue.loc[issue.loc.length - 1] ?? "");
      // Pydantic messages start with "Value error, " for custom validators; trim it.
      const msg = issue.msg.replace(/^Value error, /, "");
      if (field && !(field in fieldErrors)) fieldErrors[field] = msg;
      messages.push(field ? `${field}: ${msg}` : msg);
    }
    if (messages.length > 0) return { message: messages.join(" "), fieldErrors };
  }
  return { message: fallback, fieldErrors: {} };
}

// ---------- The one function that actually calls fetch ----------

// fetch() has no timeout by default: if the backend accepts the connection but never
// answers, the request (and the dashboard's loading skeleton) would wait forever.
const DEFAULT_TIMEOUT_MS = 8_000;

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    // fetch() only *throws* when no HTTP response arrived at all: server down, wrong
    // URL, CORS rejection, offline, or our timeout. A 404 or 500 does NOT throw.
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(`The backend at ${API_URL} did not answer within ${timeoutMs / 1000}s.`, 0);
    }
    throw new ApiError(`Cannot reach the backend at ${API_URL}. Is it running?`, 0);
  }

  if (!response.ok) {
    // The error body might not be JSON (e.g. a proxy's HTML error page), so be defensive.
    const body: unknown = await response.json().catch(() => null);
    const { message, fieldErrors } = parseErrorBody(body, response.status);
    throw new ApiError(message, response.status, fieldErrors);
  }

  if (response.status === 204) {
    // "No Content" (our DELETE). There is no body to parse.
    return undefined as T;
  }
  // `response.json()` returns Promise<any>. We trust our own backend's shape here and
  // state the type we expect; types/index.ts must mirror backend/app/schemas.py.
  return (await response.json()) as T;
}

// ---------- Public API, one function per endpoint ----------

export function getMonitors(): Promise<Monitor[]> {
  return request<Monitor[]>("/monitors");
}

export function createMonitor(input: MonitorCreateInput): Promise<Monitor> {
  return request<Monitor>("/monitors", { method: "POST", body: JSON.stringify(input) });
}

export function updateMonitor(id: number, input: MonitorUpdateInput): Promise<Monitor> {
  return request<Monitor>(`/monitors/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function deleteMonitor(id: number): Promise<void> {
  return request<void>(`/monitors/${id}`, { method: "DELETE" });
}

export function checkMonitorNow(id: number): Promise<Check> {
  // The backend may legitimately spend up to 10 s on a slow site, so allow longer.
  return request<Check>(`/monitors/${id}/check`, { method: "POST" }, 15_000);
}

export function getChecks(id: number, limit = 100): Promise<Check[]> {
  return request<Check[]>(`/monitors/${id}/checks?limit=${limit}`);
}

/** Human-readable message for any error thrown by the functions above. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
