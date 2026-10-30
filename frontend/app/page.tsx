// The dashboard. This file is a SERVER Component: it runs on the Next.js server (Node.js),
// never in the browser. That lets it fetch the first monitor list before any JavaScript
// loads, so the user sees real data in the initial HTML.
//
// CACHE COMPONENTS (enabled in next.config.ts) changes how this works compared to older
// tutorials:
// - Next.js tries to prerender every page at build time into a static "shell".
// - Our fetch to the backend is uncached (we want fresh data on every visit), so it
//   cannot be part of that shell. Such work must sit inside <Suspense>: the shell
//   contains the heading and the skeleton fallback, and the real list "streams in"
//   at request time when the fetch finishes.
// - Old tutorials would write `export const dynamic = "force-dynamic"` here. With Cache
//   Components that route segment config is not used; <Suspense> is how you mark the
//   dynamic part, and only that part, instead of the whole page.

import Link from "next/link";
import { Suspense } from "react";

import MonitorList from "@/components/MonitorList";
import MonitorListSkeleton from "@/components/MonitorListSkeleton";
import { errorMessage, getMonitors } from "@/lib/api";
import type { Monitor } from "@/types";

export default function DashboardPage() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Monitors</h1>
          <p className="text-sm text-zinc-500">Is everything up?</p>
        </div>
        <Link
          href="/monitors/new"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Add monitor
        </Link>
      </div>

      <Suspense fallback={<MonitorListSkeleton />}>
        <MonitorListLoader />
      </Suspense>
    </div>
  );
}

// An async Server Component: it can simply `await` data. Only Server Components can be
// async; Client Components fetch inside effects or event handlers instead.
async function MonitorListLoader() {
  let monitors: Monitor[] | null = null;
  let error: string | null = null;
  try {
    monitors = await getMonitors();
  } catch (e) {
    // Backend down? Don't crash the page; let MonitorList show a friendly message.
    error = errorMessage(e);
  }
  return <MonitorList initialMonitors={monitors} initialError={error} />;
}
