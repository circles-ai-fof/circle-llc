// Client-side auth helpers — single source of truth for token handling.

const TOKEN_KEY = "circle_session_token";
const EMAIL_KEY = "circle_session_email";
const EXPIRES_KEY = "circle_session_expires";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Session = {
  token: string;
  email: string;
  expiresAt: number;
};

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(TOKEN_KEY);
  const email = localStorage.getItem(EMAIL_KEY);
  const expires = localStorage.getItem(EXPIRES_KEY);
  if (!token || !email || !expires) return null;
  const expiresAt = parseInt(expires, 10);
  if (Number.isNaN(expiresAt) || expiresAt * 1000 < Date.now()) {
    clearSession();
    return null;
  }
  return { token, email, expiresAt };
}

export function storeSession(s: Session): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, s.token);
  localStorage.setItem(EMAIL_KEY, s.email);
  localStorage.setItem(EXPIRES_KEY, String(s.expiresAt));
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}

/**
 * fetch() wrapper that automatically attaches the session token.
 * On 401 it clears the session and redirects to /login.
 */
export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = getSession();
  const headers = new Headers(init.headers);
  if (session) headers.set("Authorization", `Bearer ${session.token}`);
  const url = path.startsWith("http") ? path : `${API}${path}`;
  const res = await fetch(url, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") {
    clearSession();
    const ret = encodeURIComponent(window.location.pathname);
    window.location.href = `/login?next=${ret}`;
  }
  return res;
}

export async function login(email: string): Promise<
  { ok: true; session: Session } | { ok: false; error: string; status: number }
> {
  try {
    const res = await fetch(`${API}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* not json */
      }
      return { ok: false, error: detail, status: res.status };
    }
    const data = await res.json();
    const session: Session = {
      token: data.token,
      email: data.email,
      expiresAt: data.expires_at,
    };
    storeSession(session);
    return { ok: true, session };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: `Network error: ${msg}`, status: 0 };
  }
}

export async function logout(): Promise<void> {
  try {
    await authFetch("/api/v1/auth/logout", { method: "POST" });
  } catch {
    /* swallow — local cleanup is what matters */
  }
  clearSession();
}
