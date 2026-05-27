"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getSession, authFetch, type Session } from "@/lib/auth";

const PUBLIC_PATHS = new Set<string>(["/login"]);

/**
 * Client-side gate. Redirects to /login when there is no valid session.
 * For an extra layer, also calls /api/v1/auth/me to ensure the token is
 * still valid server-side (caught revocation, expiry edge case).
 */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<"loading" | "ok" | "redirecting">("loading");
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    if (PUBLIC_PATHS.has(pathname || "")) {
      setState("ok");
      return;
    }
    const s = getSession();
    if (!s) {
      const ret = encodeURIComponent(pathname || "/");
      setState("redirecting");
      router.replace(`/login?next=${ret}`);
      return;
    }
    setSession(s);
    // Verify against the server to catch revoked or expired tokens
    authFetch("/api/v1/auth/me").then((res) => {
      if (res.ok) setState("ok");
      // authFetch already handled 401 redirect; otherwise show loader
    }).catch(() => setState("ok")); // network errors: allow optimistic access
  }, [pathname, router]);

  if (PUBLIC_PATHS.has(pathname || "")) return <>{children}</>;

  if (state !== "ok") {
    return (
      <main
        style={{
          minHeight: "100vh",
          background: "#0B0F1A",
          color: "#94a3b8",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: 28,
              height: 28,
              border: "2px solid #1e293b",
              borderTopColor: "#00D4FF",
              borderRadius: "50%",
              margin: "0 auto 12px",
              animation: "spin 0.8s linear infinite",
            }}
          />
          <div style={{ fontSize: 13 }}>
            {state === "redirecting" ? "Redirigiendo a login…" : "Validando sesión…"}
          </div>
        </div>
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </main>
    );
  }

  return (
    <>
      {/* Top-right session indicator */}
      {session && <SessionPill session={session} />}
      {children}
    </>
  );
}

function SessionPill({ session }: { session: Session }) {
  const handleLogout = async () => {
    const { logout } = await import("@/lib/auth");
    await logout();
    window.location.href = "/login";
  };
  return (
    <div
      style={{
        position: "fixed",
        top: 12,
        right: 16,
        zIndex: 100,
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 999,
        padding: "6px 14px",
        fontSize: 12,
        color: "#94a3b8",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <span style={{ color: "#00E5A0" }}>●</span>
      <span style={{ fontFamily: "monospace" }}>{session.email}</span>
      <button
        onClick={handleLogout}
        style={{
          background: "transparent",
          border: "none",
          color: "#94a3b8",
          fontSize: 11,
          cursor: "pointer",
          textDecoration: "underline",
        }}
      >
        salir
      </button>
    </div>
  );
}
