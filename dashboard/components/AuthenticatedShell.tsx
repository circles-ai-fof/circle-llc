"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

/**
 * Wraps non-login pages with the Sidebar. On /login, renders children directly
 * (no nav chrome). AuthGuard ensures unauthenticated users see /login.
 */
export default function AuthenticatedShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-surface">{children}</main>
    </div>
  );
}
