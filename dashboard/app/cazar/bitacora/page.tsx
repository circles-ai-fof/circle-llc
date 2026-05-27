"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type LinkLog = {
  id: number;
  url: string;
  source_file: string | null;
  status: string;
  idea_summary: string | null;
  sector: string | null;
  area: string | null;
  rejection_reason: string | null;
  created_at: number;
  analyzed_at: number | null;
};

type LinksLog = {
  total: number;
  by_status: Record<string, number>;
  items: LinkLog[];
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#94a3b8",
  analyzed: "#00E5A0",
  rejected: "#FFB800",
  error: "#FF4444",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "⏳ Pendiente",
  analyzed: "✓ Analizada",
  rejected: "✗ Rechazada",
  error: "⚠ Error",
};

export default function BitacoraPage() {
  const [data, setData] = useState<LinksLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");

  const refresh = async () => {
    setError(null);
    try {
      const url = filter ? `/api/v1/links?status_filter=${filter}` : "/api/v1/links";
      const r = await authFetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [filter]);

  const analyzeNow = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const r = await authFetch("/api/v1/links/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_to_analyze: 10 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      await refresh();
      alert(`Analizadas: ${d.analyzed}, rechazadas: ${d.rejected}, errores: ${d.errors}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const pendingCount = data?.by_status?.pending ?? 0;

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1400, margin: "0 auto" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
          📜 Bitácora de links
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Cada URL extraído (de archivos importados, etc.) queda registrado aquí.
          Después puedes analizarlos con LLM para extraer idea, sector y área de aplicación.
        </p>
      </header>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 20 }}>
        <Stat label="Total" value={data?.by_status ? Object.values(data.by_status).reduce((a, b) => a + b, 0) : 0} color="#00D4FF" />
        <Stat label="Pendientes" value={data?.by_status?.pending ?? 0} color="#94a3b8" />
        <Stat label="Analizadas" value={data?.by_status?.analyzed ?? 0} color="#00E5A0" />
        <Stat label="Rechazadas" value={data?.by_status?.rejected ?? 0} color="#FFB800" />
        <Stat label="Errores" value={data?.by_status?.error ?? 0} color="#FF4444" />
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <button
          onClick={analyzeNow}
          disabled={analyzing || pendingCount === 0}
          style={{
            padding: "10px 20px", background: "#00E5A0", color: "#0B0F1A",
            border: "none", borderRadius: 8, fontWeight: 700, fontSize: 14,
            cursor: analyzing || pendingCount === 0 ? "not-allowed" : "pointer",
            opacity: analyzing || pendingCount === 0 ? 0.5 : 1,
          }}
        >
          {analyzing ? "Analizando…" : `▶ Analizar ${Math.min(10, pendingCount)} pendientes`}
        </button>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            padding: "10px 12px", background: "#0F1525", color: "#fff",
            border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
          }}
        >
          <option value="">Todos los estados</option>
          <option value="pending">Solo pendientes</option>
          <option value="analyzed">Solo analizadas</option>
          <option value="rejected">Solo rechazadas</option>
          <option value="error">Solo errores</option>
        </select>
        <button
          onClick={refresh}
          style={{
            marginLeft: "auto", padding: "8px 14px", background: "transparent",
            color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6,
            fontSize: 12, cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {error && <div style={{ color: "#FF4444", padding: 12, marginBottom: 16 }}>{error}</div>}

      {loading && !data && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>Cargando…</div>
      )}

      {data && data.items.length === 0 && !loading && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>
          No hay links. Importa un archivo en <a href="/cazar/fuentes" style={{ color: "#00D4FF" }}>Fuentes</a>.
        </div>
      )}

      {data && data.items.length > 0 && (
        <div style={{ background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <Th>Estado</Th>
                <Th>URL</Th>
                <Th>Fuente</Th>
                <Th>Sector</Th>
                <Th>Área</Th>
                <Th>Resumen / razón</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => {
                const color = STATUS_COLORS[l.status] || "#94a3b8";
                return (
                  <tr key={l.id} style={{ borderBottom: "1px solid #1e293b" }}>
                    <Td>
                      <span style={{ color, fontSize: 11, fontFamily: "monospace" }}>
                        {STATUS_LABEL[l.status] || l.status}
                      </span>
                    </Td>
                    <Td mono>
                      <a
                        href={l.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "#00D4FF", textDecoration: "none" }}
                      >
                        {l.url.length > 50 ? l.url.slice(0, 50) + "…" : l.url}
                      </a>
                    </Td>
                    <Td>{l.source_file || "—"}</Td>
                    <Td>
                      {l.sector ? (
                        <span style={{
                          padding: "2px 8px", background: "rgba(0,212,255,0.1)",
                          color: "#00D4FF", borderRadius: 4, fontSize: 11,
                        }}>{l.sector}</span>
                      ) : "—"}
                    </Td>
                    <Td>{l.area || "—"}</Td>
                    <Td>
                      {l.idea_summary && (
                        <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.4 }}>
                          {l.idea_summary}
                        </div>
                      )}
                      {l.rejection_reason && (
                        <div style={{ color: "#FFB800", fontSize: 12, lineHeight: 1.4 }}>
                          {l.rejection_reason}
                        </div>
                      )}
                      {!l.idea_summary && !l.rejection_reason && (
                        <span style={{ color: "#64748b", fontSize: 12 }}>—</span>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12, padding: "12px 16px" }}>
      <div style={{ color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color, fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{ textAlign: "left", padding: "10px 14px", color: "#94a3b8", fontSize: 11, fontWeight: 500, letterSpacing: 0.5, textTransform: "uppercase" }}>
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td style={{ padding: "10px 14px", color: "#cbd5e1", fontSize: 13, fontFamily: mono ? "monospace" : "inherit", verticalAlign: "top" }}>
      {children}
    </td>
  );
}
