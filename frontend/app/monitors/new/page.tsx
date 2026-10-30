// A Server Component (the default in the App Router: no "use client" needed).
// It has no data to fetch, so Next.js can prerender it to static HTML at build time.
// Only the form inside it is interactive and ships JavaScript to the browser.

import type { Metadata } from "next";

import AddMonitorForm from "@/components/AddMonitorForm";

export const metadata: Metadata = {
  title: "Add monitor · Uptime Monitor",
};

export default function NewMonitorPage() {
  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-2xl font-semibold tracking-tight">Add a monitor</h1>
      <p className="mt-1 text-sm text-zinc-500">
        We&apos;ll send a GET request to this URL on a schedule and record whether it answers.
      </p>
      <div className="mt-6">
        <AddMonitorForm />
      </div>
    </div>
  );
}
