// /login. Nothing here depends on the visitor, so the whole page is prerendered.

import type { Metadata } from "next";

import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Log in · Uptime Monitor",
};

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
      <p className="mt-1 text-sm text-zinc-500">Enter the password for this Uptime Monitor.</p>
      <div className="mt-6">
        <LoginForm />
      </div>
    </div>
  );
}
