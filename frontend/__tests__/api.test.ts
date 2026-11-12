// lib/api.ts with a fake `fetch`, so no backend is needed.
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createMonitor, getMonitors } from "@/lib/api";

function respondWith(status: number, body: unknown) {
  const fetchMock = vi.fn(async () =>
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function errorFrom(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the call to fail");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("sends cookies, and forwards the visitor's cookie when called on the server", async () => {
    const fetchMock = respondWith(200, []);
    await getMonitors({ cookie: "uptime_session=abc" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/monitors");
    expect(init.credentials).toBe("include");
    expect(init.headers).toMatchObject({ Cookie: "uptime_session=abc" });
  });

  it("reads a plain FastAPI error", async () => {
    respondWith(404, { detail: "Monitor not found." });
    const error = await errorFrom(getMonitors());
    expect(error.status).toBe(404);
    expect(error.message).toBe("Monitor not found.");
  });

  it("turns a 422 into one message per field", async () => {
    respondWith(422, {
      detail: [
        { loc: ["body", "url"], msg: "Input should be a valid URL", type: "url_parsing" },
        { loc: ["body", "name"], msg: "Value error, Too short", type: "value_error" },
      ],
    });
    const error = await errorFrom(createMonitor({ name: "", url: "x", intervalSeconds: 60 }));
    expect(error.fieldErrors).toEqual({ url: "Input should be a valid URL", name: "Too short" });
  });

  it("copes with an error body that isn't ours", async () => {
    respondWith(502, "<html>Bad gateway</html>");
    expect((await errorFrom(getMonitors())).message).toBe("Request failed with status 502.");
  });

  it("reports an unreachable backend as a network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    const error = await errorFrom(getMonitors());
    expect(error.isNetworkError).toBe(true);
    expect(error.message).toContain("Is it running?");
  });
});
