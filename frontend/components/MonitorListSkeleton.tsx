// Shown by <Suspense> while the dashboard's data is loading on the server.
// With Cache Components this fallback is part of the prerendered static "shell", so the
// browser can paint it instantly, before the backend has even been asked for data.

export default function MonitorListSkeleton() {
  return (
    <ul className="space-y-4" aria-busy="true" aria-label="Loading monitors">
      {[0, 1, 2].map((i) => (
        <li
          key={i}
          className="animate-pulse rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div className="h-5 w-40 rounded bg-zinc-200 dark:bg-zinc-700" />
          <div className="mt-2 h-4 w-64 rounded bg-zinc-100 dark:bg-zinc-800" />
          <div className="mt-4 grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((j) => (
              <div key={j} className="h-8 rounded bg-zinc-100 dark:bg-zinc-800" />
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
