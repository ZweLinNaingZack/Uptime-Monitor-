"use client";
// Client Component because a form with live state, validation messages and a submit
// handler needs to run in the browser.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError, createMonitor, errorMessage } from "@/lib/api";

// The backend accepts any value from 30 to 86400 seconds; we offer sensible presets.
const INTERVAL_OPTIONS = [
  { seconds: 30, label: "Every 30 seconds" },
  { seconds: 60, label: "Every minute" },
  { seconds: 300, label: "Every 5 minutes" },
  { seconds: 900, label: "Every 15 minutes" },
  { seconds: 3600, label: "Every hour" },
  { seconds: 86400, label: "Every day" },
] as const;

type FieldName = "name" | "url" | "intervalSeconds";

export default function AddMonitorForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://");
  const [intervalSeconds, setIntervalSeconds] = useState(60);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // Without this the browser would do a classic full-page form POST and reload.
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await createMonitor({ name: name.trim(), url: url.trim(), intervalSeconds });
      // With Cache Components, Next.js does not unmount this page when you navigate away;
      // it hides it with React's <Activity> and keeps its state. Without this reset, coming
      // back to "Add monitor" would show the old values and a stuck "Adding…" button.
      setName("");
      setUrl("https://");
      setIntervalSeconds(60);
      setSubmitting(false);
      // Client-side navigation back to the dashboard (no full page reload).
      router.push("/");
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length > 0) {
        // 422 from FastAPI: show each message under its field.
        setFieldErrors(error.fieldErrors);
      } else {
        // 400 (e.g. blocked private URL), network failure, anything else.
        setFormError(errorMessage(error));
      }
      setSubmitting(false);
    }
  }

  const inputClass =
    "mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-700 dark:bg-zinc-900";

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      {formError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-300">
          {formError}
        </p>
      )}

      <div>
        <label htmlFor="name" className="block text-sm font-medium">
          Name
        </label>
        <input
          id="name"
          type="text"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My website"
          className={inputClass}
          aria-invalid={fieldErrors.name ? true : undefined}
        />
        <FieldError message={fieldErrors.name} />
      </div>

      <div>
        <label htmlFor="url" className="block text-sm font-medium">
          URL
        </label>
        <input
          id="url"
          type="url"
          required
          maxLength={2048}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          className={inputClass}
          aria-invalid={fieldErrors.url ? true : undefined}
        />
        <FieldError message={fieldErrors.url} />
      </div>

      <div>
        <label htmlFor="interval" className="block text-sm font-medium">
          Check interval
        </label>
        <select
          id="interval"
          value={intervalSeconds}
          // <select> values are always strings in the DOM; convert back to a number.
          onChange={(e) => setIntervalSeconds(Number(e.target.value))}
          className={inputClass}
        >
          {INTERVAL_OPTIONS.map((option) => (
            <option key={option.seconds} value={option.seconds}>
              {option.label}
            </option>
          ))}
        </select>
        <FieldError message={fieldErrors.intervalSeconds} />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {submitting ? "Adding…" : "Add monitor"}
        </button>
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          Cancel
        </Link>
      </div>
    </form>
  );
}

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-sm text-red-700 dark:text-red-400">{message}</p>;
}
