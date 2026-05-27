"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type Attempt = {
  email: string;
  ip: string | null;
  user_agent: string | null;
  ts: number;
  allowed: boolean;
  reason: string;
};

type AttemptsList = { total: number; items: Attempt[] };

export default function AuthAttemptsPage() {
  const [data, setData] = useState<AttemptsList | null>(null);
  const [loading, setLoading] = useState(true);
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fetchAttempts = async () => {
    if (!secret) return;
    setError(null);
    setLoading(true);
    try {
      const r = await authFetch("/api/v1/admin/auth-attempts?limit=500", {
        headers: { "X-Gate-Secret": secret },
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setError(`HTTP ${r.status}: ${body.detail || "unknown"}`);
        setLoading(false);
        return;
      }
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (secret) fetchAttempts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secret]);

  // Quick counts
  const allowed = data?.items.filter((i) => i.allowed).length ?? 0;
  const rejected = data?.items.filter((i) => !i.allowed).length ?? 0;
  const uniqueIPs = new Set(data?.items.map((i) => i.ip).filter(Boolean) ?? []).size;
  const uniqueEmails = new Set(data?.items.map((i) => i.email) ?? []).size;

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          Intentos de acceso
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Audit log — todos los intentos de login a la plataforma (beta cerrada).
          Útil para ver desde qué países la gente intenta conectarse antes de que
          abramos la beta.
        </p>
      </header>

      {/* Secret input */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 16,
          marginBottom: 20,
        }}
      >
        <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
          X-Gate-Secret (requerido — endpoint admin)
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Pega el GATE_RUN_SECRET de Railway"
            style={{
              flex: 1,
              padding: 10,
              background: "#0B0F1A",
              color: "#fff",
              border: "1px solid #1e293b",
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "monospace",
            }}
          />
          <button
            onClick={fetchAttempts}
            disabled={!secret || loading}
            style={{
              padding: "10px 16px",
              background: "#00D4FF",
              color: "#0B0F1A",
              border: "none",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              cursor: secret && !loading ? "pointer" : "not-allowed",
              opacity: secret && !loading ? 1 : 0.5,
            }}
          >
            {loading ? "..." : "Cargar"}
          </button>
        </div>
        {error && (
          <div style={{ color: "#FF4444", fontSize: 13, marginTop: 8 }}>{error}</div>
        )}
      </section>

      {/* Stats */}
      {data && (
        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
            marginBottom: 20,
          }}
        >
          <Stat label="Total intentos" value={data.total} accent="#00D4FF" />
          <Stat label="Permitidos" value={allowed} accent="#00E5A0" />
          <Stat label="Rechazados" value={rejected} accent="#FFB800" />
          <Stat label="IPs únicas" value={uniqueIPs} accent="#94a3b8" />
          <Stat label="Emails únicos" value={uniqueEmails} accent="#94a3b8" />
        </section>
      )}

      {/* Table */}
      {data && data.items.length > 0 && (
        <div
          style={{
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <Th>Fecha</Th>
                <Th>Email</Th>
                <Th>IP</Th>
                <Th>Estado</Th>
                <Th>Razón</Th>
                <Th>User-Agent</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                  <Td>{new Date(a.ts * 1000).toLocaleString()}</Td>
                  <Td mono>{a.email}</Td>
                  <Td mono>
                    {a.ip ? (
                      <a
                        href={`https://ipinfo.io/${a.ip}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "#00D4FF" }}
                      >
                        {a.ip}
                      </a>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>
                    <span
                      style={{
                        color: a.allowed ? "#00E5A0" : "#FFB800",
                        fontWeight: 600,
                      }}
                    >
                      {a.allowed ? "✓ OK" : "✗ Rechazado"}
                    </span>
                  </Td>
                  <Td mono>{a.reason}</Td>
                  <Td>
                    <span title={a.user_agent ?? ""}>
                      {(a.user_agent ?? "—").slice(0, 40)}
                      {(a.user_agent ?? "").length > 40 ? "…" : ""}
                    </span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>
          Aún no hay intentos de login.
        </div>
      )}
    </main>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: "14px 18px",
      }}
    >
      <div style={{ color: "#94a3b8", fontSize: 10, letterSpacing: 0.5, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ color: accent, fontSize: 26, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: "left",
        padding: "12px 16px",
        color: "#94a3b8",
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: 0.5,
        textTransform: "uppercase",
      }}
    >
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td
      style={{
        padding: "10px 16px",
        color: "#cbd5e1",
        fontSize: 13,
        fontFamily: mono ? "monospace" : "inherit",
      }}
    >
      {children}
    </td>
  );
}
