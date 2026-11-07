// Runs before every page request. (Older Next.js versions called this file middleware.ts.)
//
// This is only a convenience: it sends visitors with no session cookie to /login, before
// any page has to render. It is NOT the security check. It can't tell a real cookie from a
// made-up one, and the data isn't here anyway. The backend checks every request itself.

import { type NextRequest, NextResponse } from "next/server";

// Must match SESSION_COOKIE in backend/app/auth.py.
const SESSION_COOKIE = "uptime_session";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Every path except the login page itself and Next.js's own files.
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
