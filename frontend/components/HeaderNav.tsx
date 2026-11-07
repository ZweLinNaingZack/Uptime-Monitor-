"use client";
// The header's links. It's a Client Component because it needs the current path, to hide
// these links on the login page, and because logging out calls the API from the browser.

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logout } from "@/lib/api";

export default function HeaderNav() {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  async function handleLogout() {
    // Even if this request fails, the login page is a sensible place to end up.
    await logout().catch(() => undefined);
    // A full page load on purpose: it clears everything Next.js cached while logged in.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  return (
    <nav className="flex items-center gap-4 text-sm text-zinc-500">
      <Link href="/alerts" className="hover:underline">
        Alerts
      </Link>
      <button type="button" onClick={() => void handleLogout()} className="hover:underline">
        Log out
      </button>
    </nav>
  );
}
