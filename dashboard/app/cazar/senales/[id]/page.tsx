"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authFetch } from "@/lib/auth";

type SignalAnalysis = {
  market_size_estimate: string;
  icp_probable: string;
  competitors: string[];
  differentiator: string;
  risks: string[];
  recommendation: "promote" | "wait_for_more_data" | "discard";
  reasoning: string;
};

type Signal = {
  id: number;
  source_id: number | null;
  source_kind: string;
  source_name: string | null;
  theme: string;
  score: number;
  excerpt: string;
  evidence_urls: string[];
  suggested_topic: string;
  feedback: string | null;
  promoted_run_id: string | null;
  trend_score: number;
  published_at: number | null;
  analysis: SignalAnalysis | null;
  item_titles: string[];
  created_at: number;
};

function fmtDate(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("es-EC", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function SignalDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = parseInt(params.id, 10);

  const [signal, setSignal] = useState<Signal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [promoting, setPromoting] = useState(false);

  const refresh = async () => {
    setError(null);
    try {
      const r = await authFetch(`/api/v1/signals/${id}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSignal(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (Number.isNaN(id)) {
      setError("ID inválido");
      setLoading(false);
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const reanalyze = async () => {
    setAnalyzing(true);
    try {
      const r = await authFetch(`/api/v1/signals/${id}/analyze`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const setFeedback = async (fb: "up" | "down" | "clear") => {
    try {
      await authFetch(`/api/v1/signals/${id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: fb }),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const promote = async () => {
    if (!signal) return;
    if (
      !confirm(
        "¿Promover esta señal a una corrida completa del workflow? Cuesta ~$0.06."
      )
    )
      return;
    setPromoting(true);
    try {
      const r = await authFetch("/api/v1/gate/run-from-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_id: id }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      router.push(`/cazar?run_id=${data.run_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPromoting(false);
    }
  };

  if (loading) {
    return (
      <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", color: "#94a3b8", textAlign: "center" }}>
        Cargando señal…
      </main>
    );
  }
  if (error || !signal) {
    return (
      <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 800, margin: "0 auto" }}>
        <a href="/cazar/senales" style={{ color: "#00D4FF" }}>← Volver a Señales</a>
        <div style={{ color: "#FF4444", padding: 16, marginTop: 16 }}>
          {error || "Señal no encontrada"}
        </div>
      </main>
    );
  }

  const rec = signal.analysis?.recommendation;
  const recColor =
    rec === "promote" ? "#00E5A0" : rec === "wait_for_more_data" ? "#FFB800" : rec === "discard" ? "#FF4444" : "#94a3b8";
  const recLabel =
    rec === "promote" ? "🟢 PROMOVER"
    : rec === "wait_for_more_data" ? "🟡 ESPERAR MÁS DATA"
    : rec === "discard" ? "🔴 DESCARTAR"
    : "";
  const scoreColor =
    signal.score >= 0.8 ? "#00E5A0" : signal.score >= 0.6 ? "#FFB800" : "#94a3b8";

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 980, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <a
          href="/cazar/senales"
          style={{
            color: "#94a3b8", fontSize: 13, textDecoration: "none",
            padding: "6px 12px", border: "1px solid #1e293b", borderRadius: 6,
            display: "inline-flex", alignItems: "center", gap: 6,
          }}
        >
          ← Volver a Señales
        </a>
      </div>

      <header style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
          <span style={{ color: "#00D4FF", fontSize: 13, fontWeight: 600 }}>
            📡 {signal.source_name || signal.source_kind}
          </span>
          <span style={{
            padding: "2px 6px", background: "rgba(0,212,255,0.1)", color: "#00D4FF",
            borderRadius: 3, fontSize: 10, fontFamily: "monospace", textTransform: "uppercase",
          }}>
            {signal.source_kind}
          </span>
          <span style={{ color: scoreColor, fontSize: 13, fontWeight: 700, fontFamily: "monospace" }}>
            score {signal.score.toFixed(2)}
          </span>
          {signal.trend_score >= 1 && (
            <span style={{
              padding: "2px 8px", background: "rgba(255,184,0,0.1)", color: "#FFB800",
              borderRadius: 4, fontSize: 11, fontFamily: "monospace", fontWeight: 700,
            }}>
              🔥 trend +{signal.trend_score.toFixed(0)}
            </span>
          )}
          {signal.promoted_run_id && (
            <a
              href={`/cazar?run_id=${signal.promoted_run_id}`}
              style={{
                padding: "2px 8px", background: "rgba(0,229,160,0.1)",
                color: "#00E5A0", borderRadius: 4, fontSize: 10, textTransform: "uppercase",
                textDecoration: "none",
              }}
            >
              ✓ Ver run →
            </a>
          )}
        </div>
        <h1 style={{ color: "#fff", fontSize: 26, fontWeight: 700, lineHeight: 1.2, marginBottom: 12 }}>
          {signal.theme}
        </h1>
        <div style={{ color: "#94a3b8", fontSize: 12 }}>
          Publicado: {fmtDate(signal.published_at)} · Capturado: {fmtDate(signal.created_at)}
        </div>
      </header>

      {/* Action bar */}
      <section style={{ display: "flex", gap: 8, marginBottom: 24, flexWrap: "wrap" }}>
        <button
          onClick={() => setFeedback("up")}
          style={{
            padding: "8px 16px",
            background: signal.feedback === "up" ? "#00E5A0" : "transparent",
            color: signal.feedback === "up" ? "#0B0F1A" : "#00E5A0",
            border: "1px solid #00E5A0", borderRadius: 6, fontSize: 13, cursor: "pointer",
          }}
        >
          👍 Up
        </button>
        <button
          onClick={() => setFeedback("down")}
          style={{
            padding: "8px 16px",
            background: signal.feedback === "down" ? "#FF4444" : "transparent",
            color: signal.feedback === "down" ? "#fff" : "#FF4444",
            border: "1px solid #FF4444", borderRadius: 6, fontSize: 13, cursor: "pointer",
          }}
        >
          👎 Down
        </button>
        {signal.feedback && (
          <button
            onClick={() => setFeedback("clear")}
            style={{
              padding: "8px 14px", background: "transparent", color: "#64748b",
              border: "1px solid #1e293b", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            Limpiar feedback
          </button>
        )}
        <button
          onClick={reanalyze}
          disabled={analyzing}
          style={{
            padding: "8px 16px", background: "transparent",
            color: analyzing ? "#64748b" : "#A78BFA",
            border: `1px solid ${analyzing ? "#1e293b" : "#A78BFA"}`,
            borderRadius: 6, fontSize: 13, cursor: analyzing ? "wait" : "pointer",
          }}
        >
          {analyzing ? "Analizando…" : signal.analysis ? "🔄 Re-analizar" : "🤖 Analizar con IA"}
        </button>
        <div style={{ marginLeft: "auto" }}>
          <button
            onClick={promote}
            disabled={!!signal.promoted_run_id || promoting}
            style={{
              padding: "10px 18px",
              background: signal.promoted_run_id ? "#1e293b" : "#00D4FF",
              color: signal.promoted_run_id ? "#64748b" : "#0B0F1A",
              border: "none", borderRadius: 6, fontSize: 13, fontWeight: 700,
              cursor: signal.promoted_run_id ? "not-allowed" : promoting ? "wait" : "pointer",
            }}
          >
            {signal.promoted_run_id
              ? "Ya promovida"
              : promoting
              ? "Promoviendo…"
              : "→ Promover a idea ($0.06)"}
          </button>
        </div>
      </section>

      {/* Analysis */}
      {signal.analysis ? (
        <section
          style={{
            marginBottom: 24, padding: 20, background: "#0F1525",
            border: `1px solid ${recColor}40`, borderRadius: 12,
          }}
        >
          <div
            style={{
              padding: "12px 14px", background: `${recColor}10`,
              borderLeft: `4px solid ${recColor}`, borderRadius: 4, marginBottom: 18,
            }}
          >
            <div style={{ color: recColor, fontSize: 14, fontWeight: 700, marginBottom: 6 }}>
              {recLabel}
            </div>
            <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6 }}>
              {signal.analysis.reasoning}
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 18,
            }}
          >
            <DetailCell label="🌎 Mercado potencial" value={signal.analysis.market_size_estimate} />
            <DetailCell label="👤 ICP probable" value={signal.analysis.icp_probable} />
            <DetailCell label="💡 Diferenciador" value={signal.analysis.differentiator} />
            <DetailCell
              label="⚔️ Competencia conocida"
              value={
                signal.analysis.competitors.length
                  ? signal.analysis.competitors.join(" · ")
                  : "—"
              }
            />
          </div>

          {signal.analysis.risks.length > 0 && (
            <div style={{ marginTop: 18 }}>
              <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8, fontWeight: 600 }}>
                ⚠️ Riesgos a vigilar
              </div>
              <ul style={{ margin: 0, paddingLeft: 22, color: "#cbd5e1", fontSize: 13, lineHeight: 1.7 }}>
                {signal.analysis.risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      ) : (
        <section
          style={{
            padding: 16, background: "rgba(167,139,250,0.06)",
            border: "1px solid rgba(167,139,250,0.3)", borderRadius: 8,
            marginBottom: 24, color: "#A78BFA", fontSize: 13,
          }}
        >
          Aún no hay análisis. Click <strong>🤖 Analizar con IA</strong> arriba para
          obtener mercado, ICP, competencia, riesgos y recomendación (~$0.005).
        </section>
      )}

      {/* Excerpt */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Resumen del cazador
        </h2>
        <div
          style={{
            padding: 16, background: "#0F1525", border: "1px solid #1e293b",
            borderRadius: 8, color: "#cbd5e1", fontSize: 14, lineHeight: 1.6,
          }}
        >
          {signal.excerpt}
        </div>
      </section>

      {/* Suggested topic */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Topic sugerido (lo que se envía al workflow al promover)
        </h2>
        <div
          style={{
            padding: 14, background: "#0B0F1A", border: "1px dashed #1e293b",
            borderRadius: 8, color: "#00D4FF", fontSize: 13, fontFamily: "monospace",
          }}
        >
          {signal.suggested_topic}
        </div>
      </section>

      {/* Evidence items with full titles */}
      {signal.evidence_urls.length > 0 && (
        <section>
          <h2 style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
            Items que generaron esta señal ({signal.evidence_urls.length})
          </h2>
          <div style={{ display: "grid", gap: 8 }}>
            {signal.evidence_urls.map((u, i) => {
              const title = signal.item_titles[i] || "(sin título)";
              let host = u;
              try {
                host = new URL(u).hostname;
              } catch {
                /* invalid url, just show as-is */
              }
              return (
                <a
                  key={i}
                  href={u}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: "block", padding: 12, background: "#0F1525",
                    border: "1px solid #1e293b", borderRadius: 8, textDecoration: "none",
                  }}
                >
                  <div style={{ color: "#cbd5e1", fontSize: 14, fontWeight: 500, marginBottom: 4 }}>
                    {title}
                  </div>
                  <div style={{ color: "#00D4FF", fontSize: 11, fontFamily: "monospace" }}>
                    {host} ↗
                  </div>
                </a>
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}

function DetailCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 6, fontWeight: 600 }}>{label}</div>
      <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6 }}>{value || "—"}</div>
    </div>
  );
}
