"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  slug: string;
  ctaText: string;
  variant?: "hero" | "bottom";
};

export default function LeadForm({ slug, ctaText, variant = "hero" }: Props) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  // HONEYPOT: real users never see/fill this. Bots usually do.
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    // Store locally first (works offline; backend pickup is optional in M1)
    try {
      const stored = JSON.parse(localStorage.getItem("circles_leads") || "[]");
      stored.push({
        slug,
        email,
        name: name || null,
        ts: new Date().toISOString(),
        ua: typeof navigator !== "undefined" ? navigator.userAgent.slice(0, 200) : "",
      });
      localStorage.setItem("circles_leads", JSON.stringify(stored));
    } catch {
      /* localStorage disabled — non-fatal */
    }

    // POST to API if configured. Backend enforces full anti-bot stack.
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      if (apiUrl) {
        const turnstileEl =
          typeof document !== "undefined"
            ? (document.querySelector(
                'input[name="cf-turnstile-response"]',
              ) as HTMLInputElement | null)
            : null;
        const turnstileToken = turnstileEl?.value || null;

        const res = await fetch(`${apiUrl}/api/v1/leads`, {
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
          signal: AbortSignal.timeout(6000),
        });
        if (res.status === 400 || res.status === 401 || res.status === 429) {
          const body = await res.json().catch(() => ({ detail: "Rechazado" }));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
      }
    } catch (e) {
      // Soft-fail: localStorage copy is the safety net
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("Disposable") || msg.includes("Bot-check") || msg.includes("moment")) {
        setSubmitting(false);
        setError(msg);
        return;
      }
      /* otherwise just continue — local copy already saved */
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
        ✓ Recibido. Te avisaremos en máximo 14 días si seguimos adelante con esta fábrica.
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
    </form>
  );
}
