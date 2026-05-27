"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type RunSummary = {
  run_id: string;
  idea_title: string;
  verdict: string;
  confidence: number;
  landing_slug: string;
  needs_human_review: boolean;
  has_override: boolean;
  cost_usd_estimated: number;
  steps_used: number;
};

type Column = {
  phase: string;
  label: string;
  count: number;
  runs: RunSummary[];
};

type Pipeline = { total_runs: number; columns: Column[] };

const PHASE_STYLES: Record<string, { bg: string; border: string; chip: string }> = {
  pending_review: { bg: "rgba(255,184,0,0.08)", border: "#FFB80050", chip: "#FFB800" },
  iterate: { bg: "rgba(0,212,255,0.06)", border: "#00D4FF50", chip: "#00D4FF" },
  pass: { bg: "rgba(0,229,160,0.06)", border: "#00E5A050", chip: "#00E5A0" },
  kill: { bg: "rgba(255,68,68,0.06)", border: "#FF444450", chip: "#FF4444" },
  overridden: { bg: "rgba(168,85,247,0.06)", border: "#A855F750", chip: "#A855F7" },
};

const REFRESH_MS = 8000;

export default function PipelinePage() {
  const [data, setData] = useState<Pipeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(0);

  const refresh = async () => {
    setError(null);
    try {
      const r = await authFetch("/api/v1/pipeline");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setLastUpdate(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1600, margin: "0 auto" }}>
      <header style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 4 }}>
            📊 Pipeline de fábricas
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 14 }}>
            Cada idea atraviesa las fases de izquierda a derecha. Auto-refresh cada 8s.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>
            {data ? <strong style={{ color: "#fff" }}>{data.total_runs}</strong> : "…"} runs totales
          </div>
          <div style={{ color: "#64748b", fontSize: 11, fontFamily: "monospace" }}>
            {lastUpdate ? `↻ ${new Date(lastUpdate).toLocaleTimeString()}` : ""}
          </div>
          <button
            onClick={refresh}
            style={{
              padding: "6px 14px", background: "transparent", color: "#00D4FF",
              border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </header>

      {/* Flow diagram */}
      <div
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 16,
          marginBottom: 20,
          color: "#94a3b8",
          fontSize: 12,
          fontFamily: "monospace",
          textAlign: "center",
        }}
      >
        🎯 Hunter → 🔍 Enricher → 🧠 Maturer → 📊 Validator → ✍️ Landing → ⚖️ <strong style={{ color: "#fff" }}>Decisión</strong>
        <span style={{ marginLeft: 12, color: "#64748b" }}>(las fábricas terminan en una de las 5 columnas)</span>
      </div>

      {error && (
        <div style={{ color: "#FF4444", padding: 16, marginBottom: 16, background: "rgba(255,68,68,0.08)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading && !data && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>Cargando…</div>
      )}

      {data && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(5, 1fr)",
            gap: 12,
            alignItems: "flex-start",
          }}
        >
          {data.columns.map((col) => {
            const s = PHASE_STYLES[col.phase] || { bg: "#0F1525", border: "#1e293b", chip: "#94a3b8" };
            return (
              <div
                key={col.phase}
                style={{
                  background: s.bg,
                  border: `1px solid ${s.border}`,
                  borderRadius: 12,
                  padding: 12,
                  minHeight: 200,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ color: s.chip, fontSize: 13, fontWeight: 700 }}>{col.label}</div>
                  <div style={{
                    background: s.chip, color: "#0B0F1A", borderRadius: 999,
                    padding: "1px 10px", fontSize: 11, fontWeight: 700, fontFamily: "monospace",
                  }}>
                    {col.count}
                  </div>
                </div>
                {col.runs.length === 0 ? (
                  <div style={{ color: "#475569", fontSize: 12, fontStyle: "italic", padding: 12, textAlign: "center" }}>
                    sin fábricas en esta fase
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {col.runs.map((r) => <RunCard key={r.run_id} r={r} chipColor={s.chip} />)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}

function RunCard({ r, chipColor }: { r: RunSummary; chipColor: string }) {
  return (
    <div
      style={{
        background: "#0B0F1A",
        border: "1px solid #1e293b",
        borderRadius: 8,
        padding: 10,
      }}
    >
      <div style={{ color: "#fff", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
        {r.idea_title || "(sin título)"}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", fontSize: 10, color: "#94a3b8" }}>
        <span style={{ background: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 4, fontFamily: "monospace" }}>
          conf {(r.confidence * 100).toFixed(0)}%
        </span>
        <span style={{ background: "rgba(255,255,255,0.05)", padding: "1px 6px", borderRadius: 4, fontFamily: "monospace" }}>
          ${r.cost_usd_estimated.toFixed(2)}
        </span>
        {r.has_override && (
          <span style={{ background: "rgba(168,85,247,0.15)", color: "#A855F7", padding: "1px 6px", borderRadius: 4 }}>
            ⚖️ override
          </span>
        )}
      </div>
      <div style={{ marginTop: 6 }}>
        {r.landing_slug && (
          <a
            href={`https://circles-ai.ai/f/${r.landing_slug}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: chipColor, fontSize: 10, textDecoration: "none", fontFamily: "monospace" }}
          >
            /f/{r.landing_slug.slice(0, 30)} →
          </a>
        )}
      </div>
    </div>
  );
}
