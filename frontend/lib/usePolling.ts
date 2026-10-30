// A custom hook: a plain function whose name starts with "use" and that calls other
// hooks. It lets the dashboard and the detail page share the same polling behaviour
// instead of copying the effect into both.

import { useEffect } from "react";

/**
 * Calls `refresh` right away, then every `intervalMs` while the browser tab is visible,
 * and again as soon as the user comes back to the tab.
 *
 * `refresh` should be wrapped in useCallback by the caller. When it changes (because
 * its own dependencies changed, e.g. a different time period), the effect restarts and
 * fetches immediately, which is exactly what we want.
 */
export function usePolling(refresh: () => void, intervalMs: number): void {
  useEffect(() => {
    // Why refresh immediately, even when the server already sent fresh data? With Cache
    // Components, Next.js keeps visited pages alive inside React's <Activity> instead of
    // unmounting them. Coming back to a page *shows it again* with its OLD state (new
    // props from the server don't reset useState). Activity cleans up effects when
    // hiding a page and re-runs them when showing it, so this line runs on every return.
    refresh();

    const intervalId = setInterval(() => {
      // Don't poll while the browser tab is in the background: nobody is looking.
      if (document.visibilityState === "visible") refresh();
    }, intervalMs);

    // When the user returns to this browser tab, update right away instead of waiting
    // for the next tick.
    function handleVisibilityChange() {
      if (document.visibilityState === "visible") refresh();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    // Cleanup: runs when the component unmounts, is hidden by <Activity>, or before the
    // effect re-runs. Forgetting this would leave timers running forever, multiplying
    // on every visit.
    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refresh, intervalMs]);
}
