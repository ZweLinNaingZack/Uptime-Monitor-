// Login helpers for Server Components.
//
// `import "server-only"` makes the build fail if a Client Component ever imports this file.
// `cookies()` only works on the server, and this keeps that mistake from reaching a browser.

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, type RequestAuth } from "@/lib/api";

/**
 * The visitor's cookies, ready to send to the backend.
 *
 * With Cache Components, reading cookies counts as request-time data, so this must be
 * called inside <Suspense>. Every loader that uses it already is.
 */
export async function forwardedAuth(): Promise<RequestAuth> {
  const cookieStore = await cookies();
  return { cookie: cookieStore.toString() };
}

/**
 * Send a logged-out visitor to /login. Call it first in a loader's `catch`.
 *
 * proxy.ts only checks that a cookie EXISTS. An expired one gets past it, and the backend,
 * which makes the real decision, answers 401. This is where that case is handled.
 */
export function redirectIfLoggedOut(error: unknown): void {
  if (error instanceof ApiError && error.status === 401) redirect("/login");
}
