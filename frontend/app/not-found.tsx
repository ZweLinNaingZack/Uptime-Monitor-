// Rendered whenever notFound() is called or no route matches the URL.

import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
      <h1 className="text-xl font-semibold">Not found</h1>
      <p className="mt-1 text-sm text-zinc-500">That monitor or page doesn&apos;t exist.</p>
      <Link href="/" className="mt-4 inline-block text-sm underline">
        Back to all monitors
      </Link>
    </div>
  );
}
