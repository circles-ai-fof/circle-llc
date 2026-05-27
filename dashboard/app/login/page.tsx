"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginInner />
    </Suspense>
  );
}

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = params.get("next") || "/";

  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waitlisted, setWaitlisted] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setWaitlisted(false);

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Email inválido");
      return;
    }

    setSubmitting(true);
    const result = await login(email);
    setSubmitting(false);

    if (result.ok) {
      router.push(nextPath);
      return;
    }

    // 403 = not on allowlist → show friendly waitlist message
    if (result.status === 403) {
      setWaitlisted(true);
      return;
    }
    setError(result.error);
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(ellipse at top, rgba(0,212,255,0.08), transparent 60%), #0B0F1A",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 16,
          padding: 32,
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div
            style={{
              display: "inline-block",
              padding: "4px 12px",
              borderRadius: 999,
              background: "rgba(0,212,255,0.1)",
              border: "1px solid rgba(0,212,255,0.3)",
              color: "#00D4FF",
              fontSize: 11,
              fontWeight: 500,
              marginBottom: 16,
              letterSpacing: 0.5,
            }}
          >
            BETA CERRADA
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>
            Acceso a la plataforma
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            Ingresa tu email para acceder. La plataforma está habilitada solo
            para usuarios beta.
          </p>
        </div>

        {waitlisted ? (
          <div
            style={{
              background: "rgba(255,184,0,0.1)",
              border: "1px solid rgba(255,184,0,0.3)",
              borderRadius: 12,
              padding: 20,
              textAlign: "center",
              color: "#FFB800",
            }}
          >
            <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>
              Aún no estás habilitado
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.5, color: "#cbd5e1" }}>
              La plataforma está habilitada solo para usuarios de la beta cerrada.
              Tu email <strong style={{ color: "#fff" }}>{email}</strong> quedó
              registrado en la lista de espera — te avisaremos cuando esté
              disponible.
            </div>
            <button
              onClick={() => {
                setWaitlisted(false);
                setEmail("");
              }}
              style={{
                marginTop: 16,
                padding: "8px 16px",
                background: "transparent",
                color: "#94a3b8",
                border: "1px solid #1e293b",
                borderRadius: 8,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              ← Probar con otro email
            </button>
          </div>
        ) : (
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="tu@email.com"
              required
              autoComplete="email"
              autoFocus
              style={{
                padding: "14px 16px",
                background: "#0B0F1A",
                border: "1px solid #1e293b",
                borderRadius: 10,
                color: "#fff",
                fontSize: 15,
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
              {submitting ? "Validando…" : "Acceder"}
            </button>
            {error && (
              <div
                style={{
                  color: "#FF4444",
                  fontSize: 13,
                  padding: "8px 12px",
                  background: "rgba(255,68,68,0.08)",
                  border: "1px solid rgba(255,68,68,0.2)",
                  borderRadius: 8,
                }}
              >
                {error}
              </div>
            )}
          </form>
        )}

        <div
          style={{
            marginTop: 24,
            paddingTop: 16,
            borderTop: "1px solid #1e293b",
            textAlign: "center",
            color: "#64748b",
            fontSize: 11,
          }}
        >
          circles-ai.ai · Factory of Factories
        </div>
      </div>
    </main>
  );
}
