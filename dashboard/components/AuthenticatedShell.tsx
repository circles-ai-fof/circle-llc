"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

/**
 * Wraps non-login pages with the Sidebar. On /login, renders children directly
 * (no nav chrome). AuthGuard ensures unauthenticated users see /login.
 *
 * Mobile: sidebar is hidden by default, toggled with a hamburger button.
 * Desktop (>= md): sidebar always visible.
 */
export default function AuthenticatedShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";
  const [open, setOpen] = useState(false);

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile: hamburger button (fixed top-left) */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle menu"
        className="md:hidden fixed top-3 left-3 z-40 p-2 rounded-md"
        style={{
          backgroundColor: "#1E2A3A",
          color: "#00D4FF",
          border: "1px solid rgba(0,212,255,0.3)",
        }}
      >
        {open ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        )}
      </button>

      {/* Mobile overlay backdrop */}
      {open && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setOpen(false)}
          className="md:hidden fixed inset-0 z-20 bg-black/60"
        />
      )}

      {/* Sidebar — fixed off-canvas on mobile, static on desktop */}
      <div
        className={`md:static md:translate-x-0 fixed inset-y-0 left-0 z-30 transform transition-transform duration-200 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar onNavigate={() => setOpen(false)} />
      </div>

      <main className="flex-1 overflow-y-auto bg-surface">
        {/* Mobile: top padding so hamburger doesn't overlap content */}
        <div className="md:pt-0 pt-14">{children}</div>
      </main>
    </div>
  );
}
