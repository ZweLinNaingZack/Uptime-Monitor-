"use client";
// Set up one alert channel. The form never shows a saved secret, because the API has no way
// to return one. It can only replace the value or remove it.

import { type FormEvent, useState } from "react";

import { errorMessage, removeChannel, saveDiscordChannel, saveTelegramChannel } from "@/lib/api";
import type { AlertChannel } from "@/types";

interface ChannelSettingsFormProps {
  channel: AlertChannel;
  /** The API answers every change with the new channel list. */
  onChannelsChange: (channels: AlertChannel[]) => void;
}

const INPUT_CLASS =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 font-mono text-sm dark:border-zinc-700 dark:bg-zinc-900";

export default function ChannelSettingsForm({ channel, onChannelsChange }: ChannelSettingsFormProps) {
  const [secret, setSecret] = useState("");
  const [chatId, setChatId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTelegram = channel.name === "telegram";

  async function run(action: () => Promise<AlertChannel[]>) {
    setBusy(true);
    setError(null);
    try {
      onChannelsChange(await action());
      // Don't leave a secret sitting in the page once it's saved.
      setSecret("");
      setChatId("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void run(() => (isTelegram ? saveTelegramChannel(secret, chatId) : saveDiscordChannel(secret)));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      {channel.source === "env" && (
        <p className="text-xs text-zinc-500">
          Currently set in <code className="font-mono">backend/.env</code>. Saving here overrides it.
        </p>
      )}
      <div>
        <label htmlFor={`${channel.name}-secret`} className="mb-1 block text-xs font-medium">
          {isTelegram ? "Bot token" : "Webhook URL"}
        </label>
        <input
          id={`${channel.name}-secret`}
          // type="password" hides it on screen, in case someone is looking over your shoulder.
          type="password"
          // Stops password managers from offering to fill in or save this value.
          autoComplete="off"
          required
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          placeholder={channel.configured ? "Saved. Enter a new value to replace it." : undefined}
          className={INPUT_CLASS}
        />
      </div>
      {isTelegram && (
        <div>
          <label htmlFor="telegram-chat" className="mb-1 block text-xs font-medium">
            Chat ID
          </label>
          <input
            id="telegram-chat"
            type="text"
            autoComplete="off"
            required
            value={chatId}
            onChange={(event) => setChatId(event.target.value)}
            className={INPUT_CLASS}
          />
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {channel.source === "dashboard" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => removeChannel(channel.name))}
            className="rounded-md px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950"
          >
            Remove
          </button>
        )}
      </div>
    </form>
  );
}
