// A hook that returns the current time and re-renders the component every second, so
// "last check: 12s ago" keeps ticking.
//
// THE HYDRATION PROBLEM this solves:
// A Client Component is rendered twice: once on the server (to produce HTML quickly),
// and again in the browser ("hydration"), where React expects to produce the SAME output
// and attach event handlers to the existing HTML. If we called Date.now() during render,
// the server might print "12s ago" and the browser, a moment later, "13s ago". React
// would report a hydration mismatch. Timezones cause the same problem for formatted
// dates: the server's timezone is not the user's.
//
// The fix: during the server render AND the hydration render, return `null` ("time not
// known yet") so both outputs match. Right after hydration React switches to the real
// clock. `useSyncExternalStore` supports exactly this through `getServerSnapshot`.

import { useSyncExternalStore } from "react";

const TICK_MS = 1000;

// One shared timer for all components on the page, instead of one interval per card.
let now = 0;
let timer: ReturnType<typeof setInterval> | undefined;
const listeners = new Set<() => void>();

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  if (timer === undefined) {
    // Refresh a possibly stale value from an earlier visit. React re-reads the snapshot
    // right after subscribing, so components pick this up immediately.
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((listener) => listener());
    }, TICK_MS);
  }
  // Cleanup: stop the timer when the last component using it unmounts.
  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0 && timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function getSnapshot(): number {
  // Must return the SAME value on every call until the store changes (React compares
  // results and warns about an infinite loop otherwise), so we never read the clock
  // here except for the very first time.
  if (now === 0) now = Date.now();
  return now;
}

function getServerSnapshot(): null {
  return null;
}

/** Current time in ms, or `null` during server rendering and hydration. */
export function useNow(): number | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
