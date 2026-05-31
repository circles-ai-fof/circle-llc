"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M7.0 — Admin Status page
 *
 * Visualización del estado completo del sistema:
 * - Mode (live/mock), storage, CORS
 * - 13 agentes con version + status + sprint origen
 * - env vars check (sin leakear secrets)
 * - Crons con secret keys requeridas vs presentes
 */

type AgentStatus = {
  name: string;
  version: string;
  status: string;
  experimental: boolean;
  sprint_origin: string;
};

type EnvCheck = {
  name: string;
  set: boolean;
  masked_value: string | null;
};

type CronStatus = {
  name: string;
  schedule: string;
  secret_keys_required: string[];
  secret_keys_present: boolean[];
};

type AdminStatus = {
  mode: string;
  persistent_storage: boolean;
  db_path: string | null;
  cors_origins_count: number;
  allowed_emails_count: number;
  sources_total: number;
  sources_active: number;
  signals_total: number;
  runs_total: number;
  agents: AgentStatus[];
  env_checks: EnvCheck[];
  crons: CronStatus[];
};

const STATUS_COLORS: Record<string, string> = {
  "active(workflow)": "#00E5A0",
  "active(on-demand)": "#00D4FF",
  "experimental": "#FFB800",
  "deferred": "#94a3b8",
};

export default function AdminStatusPage() {
  const [data, setData] = useState<AdminStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authFetch("/api/v1/admin/status");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  if (loading && !data) {
    return <main style={{ padding: 32, color: "#94a3b8", textAlign: "center" }}>Cargando estado del sistema…</main>;
  }

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
            🛠️ Admin Status
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            Estado interno del sistema: agentes, env vars, crons, stats.
          </p>
        </div>
        <button
          onClick={refresh}
          style={{
            marginLeft: "auto", padding: "6px 14px", background: "transparent",
            color: "#00D4FF", border: "1px solid #00D4FF",
            borderRadius: 6, fontSize: 13, cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </header>

      {error && (
        <div style={{ color: "#FF4444", padding: 12, marginBottom: 16, background: "rgba(255,68,68,0.06)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Sección 1: Top stats */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 24 }}>
            <StatCard label="Modo" value={data.mode} accent={data.mode === "live" ? "#00E5A0" : "#FFB800"} />
            <StatCard label="Storage" value={data.persistent_storage ? "Persistente" : "Memoria"} accent={data.persistent_storage ? "#00E5A0" : "#FFB800"} />
            <StatCard label="Agentes" value={String(data.agents.length)} accent="#00D4FF" />
            <StatCard label="Fuentes" value={`${data.sources_active}/${data.sources_total}`} accent="#A78BFA" />
            <StatCard label="Señales" value={String(data.signals_total)} accent="#00D4FF" />
            <StatCard label="Runs" value={String(data.runs_total)} accent="#A78BFA" />
            <StatCard label="CORS origins" value={String(data.cors_origins_count)} accent="#94a3b8" />
            <StatCard label="Allowlist emails" value={String(data.allowed_emails_count)} accent="#94a3b8" />
          </section>

          {/* Sección 2: Agentes */}
          <Section title="🤖 Agentes registrados">
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#0B0F1A", borderBottom: "1px solid #1e293b" }}>
                    <Th>Agente</Th>
                    <Th>Version</Th>
                    <Th>Status</Th>
                    <Th>Sprint origen</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.agents.map((a) => (
                    <tr key={a.name} style={{ borderBottom: "1px solid #1e293b" }}>
                      <td style={{ padding: "10px 12px", color: "#cbd5e1", fontFamily: "monospace" }}>{a.name}</td>
                      <td style={{ padding: "10px 12px", color: "#94a3b8", fontFamily: "monospace", fontSize: 11 }}>{a.version}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <span style={{
                          color: STATUS_COLORS[a.status] || "#94a3b8",
                          fontSize: 11, fontWeight: 600,
                          padding: "2px 8px",
                          background: `${STATUS_COLORS[a.status] || "#94a3b8"}15`,
                          border: `1px solid ${STATUS_COLORS[a.status] || "#94a3b8"}40`,
                          borderRadius: 4,
                        }}>
                          {a.status}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px", color: "#64748b", fontSize: 11 }}>{a.sprint_origin}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {/* Sección 3: Env vars */}
          <Section title="🔐 Variables de entorno">
            <p style={{ color: "#64748b", fontSize: 11, marginBottom: 12 }}>
              Variables secretas (API keys, passwords) muestran solo set/unset. Variables de config muestran preview.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 8 }}>
              {data.env_checks.map((e) => (
                <div key={e.name} style={{
                  padding: "8px 12px",
                  background: e.set ? "rgba(0,229,160,0.06)" : "rgba(255,184,0,0.06)",
                  border: `1px solid ${e.set ? "rgba(0,229,160,0.3)" : "rgba(255,184,0,0.3)"}`,
                  borderRadius: 6,
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 8,
                }}>
                  <span style={{ color: "#cbd5e1", fontSize: 12, fontFamily: "monospace" }}>{e.name}</span>
                  <span style={{ color: e.set ? "#00E5A0" : "#FFB800", fontSize: 11, fontWeight: 700 }}>
                    {e.set ? (e.masked_value ?? "✓ SET") : "✗ NO SET"}
                  </span>
                </div>
              ))}
            </div>
          </Section>

          {/* Sección 4: Crons */}
          <Section title="⏰ Crons configurados">
            {data.crons.map((c) => {
              const allPresent = c.secret_keys_present.every((b) => b);
              return (
                <div key={c.name} style={{
                  marginBottom: 12, padding: 12,
                  background: "#0F1525",
                  border: `1px solid ${allPresent ? "rgba(0,229,160,0.3)" : "rgba(255,184,0,0.3)"}`,
                  borderRadius: 8,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <strong style={{ color: "#fff" }}>{c.name}</strong>
                    <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: "monospace" }}>{c.schedule}</span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 4 }}>
                    {c.secret_keys_required.map((k, i) => (
                      <div key={k} style={{ fontSize: 11, color: "#cbd5e1", display: "flex", justifyContent: "space-between" }}>
                        <code style={{ background: "#0B0F1A", padding: "1px 6px", borderRadius: 3 }}>{k}</code>
                        <span style={{ color: c.secret_keys_present[i] ? "#00E5A0" : "#FF4444" }}>
                          {c.secret_keys_present[i] ? "✓" : "✗"}
                        </span>
                      </div>
                    ))}
                  </div>
                  {!allPresent && (
                    <div style={{ marginTop: 8, color: "#FFB800", fontSize: 11, fontStyle: "italic" }}>
                      ⚠️ Faltan secrets — cron salta silencioso (no falla, no envía).
                    </div>
                  )}
                </div>
              );
            })}
          </Section>

          {data.db_path && (
            <div style={{ marginTop: 24, padding: 12, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 8, color: "#64748b", fontSize: 11, fontFamily: "monospace" }}>
              DB: {data.db_path}
            </div>
          )}
        </>
      )}
    </main>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div style={{
      padding: 12, background: "#0F1525", border: "1px solid #1e293b",
      borderRadius: 8, textAlign: "center",
    }}>
      <div style={{ color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color: accent, fontSize: 18, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 24, padding: 16, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12 }}>
      <h2 style={{ color: "#fff", fontSize: 14, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{
      textAlign: "left", padding: "10px 12px",
      color: "#94a3b8", fontSize: 10, fontWeight: 600,
      textTransform: "uppercase", letterSpacing: 0.5,
    }}>
      {children}
    </th>
  );
}
