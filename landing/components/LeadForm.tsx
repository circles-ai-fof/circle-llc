"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  slug: string;
  ctaText: string;
  variant?: "hero" | "bottom";
};

// Baked at build time. If undefined, the form will warn the user.
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function LeadForm({ slug, ctaText, variant = "hero" }: Props) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  // HONEYPOT: real users never see/fill this. Bots usually do.
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  // null = none, string = error
  const [error, setError] = useState<string | null>(null);
  // Track if API confirmed the save (vs only-localStorage fallback)
  const [serverConfirmed, setServerConfirmed] = useState(false);

  // Track time on page → block obviously-bot-fast submissions
  const mountedAt = useRef<number>(0);
  useEffect(() => {
    mountedAt.current = Date.now();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Email inválido");
      return;
    }

    const dwellMs = Date.now() - (mountedAt.current || Date.now());
    if (dwellMs < 1500) {
      setError("Tómate un segundo más, por favor.");
      return;
    }

    setSubmitting(true);

    // Always backup to localStorage first — this never fails.
    let backedUp = false;
    try {
      const stored = JSON.parse(localStorage.getItem("circles_leads") || "[]");
      stored.push({
        slug,
        email,
        name: name || null,
        ts: new Date().toISOString(),
        ua: typeof navigator !== "undefined" ? navigator.userAgent.slice(0, 200) : "",
        confirmed: false, // updated after server ack
      });
      localStorage.setItem("circles_leads", JSON.stringify(stored));
      backedUp = true;
    } catch {
      /* localStorage disabled — non-fatal */
    }

    // ---- Server submit ----
    // If NEXT_PUBLIC_API_URL isn't baked, surface it immediately.
    if (!API_URL) {
      setSubmitting(false);
      setError(
        "Configuración pendiente: NEXT_PUBLIC_API_URL no está disponible. " +
          (backedUp ? "Tu email quedó guardado localmente." : "No se guardó.")
      );
      return;
    }

    const turnstileEl =
      typeof document !== "undefined"
        ? (document.querySelector(
            'input[name="cf-turnstile-response"]',
          ) as HTMLInputElement | null)
        : null;
    const turnstileToken = turnstileEl?.value || null;

    try {
      const res = await fetch(`${API_URL}/api/v1/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug,
          email,
          name: name || null,
          company_website: companyWebsite || null, // honeypot
          dwell_ms: dwellMs,
          turnstile_token: turnstileToken,
        }),
        signal: AbortSignal.timeout(8000),
      });

      // Treat any non-2xx as user-visible error so we never falsely show "Recibido".
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch {
          /* body not JSON */
        }
        setSubmitting(false);
        setError(
          `${detail} — Tu email quedó guardado localmente, lo recuperaremos manualmente.`
        );
        // Mark localStorage entry as unconfirmed (already false by default)
        return;
      }

      // 2xx: parse server payload to confirm accepted=true
      let serverSays: { accepted?: boolean } = {};
      try {
        serverSays = await res.json();
      } catch {
        /* tolerate missing body */
      }

      if (serverSays.accepted !== false) {
        setServerConfirmed(true);
        // Update localStorage entry to mark confirmed=true
        try {
          const stored = JSON.parse(localStorage.getItem("circles_leads") || "[]");
          if (stored.length > 0) {
            stored[stored.length - 1].confirmed = true;
            localStorage.setItem("circles_leads", JSON.stringify(stored));
          }
        } catch {
          /* ignore */
        }
      }
    } catch (e) {
      // Network / CORS / timeout
      const msg = e instanceof Error ? e.message : String(e);
      setSubmitting(false);
      setError(
        `No pude contactar al servidor (${msg}). Tu email quedó guardado localmente.`
      );
      return;
    }

    setDone(true);
    setSubmitting(false);
  };

  if (done) {
    return (
      <div
        style={{
          background: "rgba(0,229,160,0.1)",
          border: "1px solid rgba(0,229,160,0.3)",
          borderRadius: 10,
          padding: 16,
          color: "#00E5A0",
          fontSize: 14,
        }}
      >
        ✓ Recibido{serverConfirmed ? "" : " (guardado local)"}. Te avisaremos en
        máximo 14 días si seguimos adelante con esta fábrica.
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {/* HONEYPOT — visually hidden, but bots still fill it */}
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          left: "-10000px",
          top: "auto",
          width: 1,
          height: 1,
          overflow: "hidden",
        }}
      >
        <label htmlFor="company_website">Company website (leave blank)</label>
        <input
          id="company_website"
          name="company_website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={companyWebsite}
          onChange={(e) => setCompanyWebsite(e.target.value)}
        />
      </div>

      {variant === "bottom" && (
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tu nombre (opcional)"
          autoComplete="name"
          style={{
            padding: "14px 16px",
            background: "rgba(255,255,255,0.05)",
            border: "1px solid #1e293b",
            borderRadius: 10,
            color: "#fff",
            fontSize: 15,
            fontFamily: "inherit",
            outline: "none",
          }}
        />
      )}
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="tu@email.com"
        required
        autoComplete="email"
        style={{
          padding: "14px 16px",
          background: "rgba(255,255,255,0.05)",
          border: "1px solid #1e293b",
          borderRadius: 10,
          color: "#fff",
          fontSize: 15,
          fontFamily: "inherit",
          outline: "none",
        }}
      />
      <button
        type="submit"
        disabled={submitting}
        style={{
          padding: "14px 20px",
          background: "#00D4FF",
          color: "#0B0F1A",
          border: "none",
          borderRadius: 10,
          fontWeight: 700,
          fontSize: 15,
          cursor: submitting ? "wait" : "pointer",
          opacity: submitting ? 0.6 : 1,
        }}
      >
        {submitting ? "Enviando..." : ctaText}
      </button>
      {error && (
        <div style={{ color: "#FF4444", fontSize: 13, marginTop: 4 }}>{error}</div>
      )}
      {/* Debug footer — visible only when NEXT_PUBLIC_DEBUG=1 at build */}
      {process.env.NEXT_PUBLIC_DEBUG === "1" && (
        <div style={{ color: "#64748b", fontSize: 11, marginTop: 8, fontFamily: "monospace" }}>
          API: {API_URL ?? "❌ NEXT_PUBLIC_API_URL undefined"}
        </div>
      )}
    </form>
  );
}
