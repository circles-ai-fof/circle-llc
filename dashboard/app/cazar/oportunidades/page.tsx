"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M4.11 — Oportunidades cross-country (first-mover gaps).
 *
 * Inspirado en el audio del founder (29-may): "si llegas first-mover ahí,
 * eventualmente tienes posibilidades de poderla reventar". La página muestra
 * clusters de ideas validadas en algún país (≥2 señales + ≥1 👍) y los países
 * objetivo donde NO existe ningún signal — son los huecos donde podemos llegar
 * primero.
 *
 * Cómo se lee:
 *   filas    = ideas/clusters detectados
 *   columnas = países (LATAM + USA + España por defecto)
 *   celda verde   = idea ya validada en ese país
 *   celda roja    = idea NO existe en ese país → FIRST-MOVER GAP
 *   celda gris    = sin data
 */

type CountryValidation = {
  country: string;
  signals: number;
  ups: number;
  downs: number;
  sample_themes: string[];
};

type TrendGapItem = {
  idea_summary: string;
  cluster_size: number;
  validated_in: CountryValidation[];
  missing_in: string[];
  opportunity_score: number;
};

// M5.0 — TrendGapAnalyzer (agente experimental)
type TrendGapAnalysis = {
  priority_country: string;
  priority_rationale: string;
  timing_hypothesis: string;
  adoption_pattern: string;
  go_to_market: string[];
  risks_per_country: Record<string, string>;
  effort_estimate_weeks: string;
  confidence: number;
  reasoning: string;
  cost_usd_estimated: number;
  mock_mode: boolean;
};

const DEFAULT_COUNTRIES = [
  "Ecuador", "México", "Colombia", "Perú", "Chile",
  "Argentina", "Brasil", "Estados Unidos", "España",
];

export default function OportunidadesPage() {
  const [items, setItems] = useState<TrendGapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minSignals, setMinSignals] = useState(2);
  const [minFeedback, setMinFeedback] = useState(1);
  const [countries] = useState<string[]>(DEFAULT_COUNTRIES);
  // M5.0 — análisis con LLM agent experimental
  const [analyzing, setAnalyzing] = useState<number | null>(null);
  const [analysisByIdx, setAnalysisByIdx] = useState<Record<number, TrendGapAnalysis>>({});

  const analyze = async (idx: number, item: TrendGapItem) => {
    if (analyzing !== null) return;
    setAnalyzing(idx);
    try {
      const r = await authFetch("/api/v1/trend-gaps/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idea_summary: item.idea_summary,
          validated_in: item.validated_in,
          missing_in: item.missing_in,
          opportunity_score: item.opportunity_score,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: TrendGapAnalysis = await r.json();
      setAnalysisByIdx((prev) => ({ ...prev, [idx]: data }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(null);
    }
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        min_validation_signals: String(minSignals),
        min_validation_feedback: String(minFeedback),
        countries: countries.join(","),
      });
      const r = await authFetch(`/api/v1/trend-gaps?${params.toString()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setItems(d.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minSignals, minFeedback]);

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1400, margin: "0 auto" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          🌎 Oportunidades cross-country
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14, lineHeight: 1.6, maxWidth: 720 }}>
          Detecta ideas <strong>validadas en un país</strong> que <strong>no
          existen en otros</strong> — son tus oportunidades de first-mover.
          Inspirado en el modelo del founder: <em>"si llegas primero ahí,
          tienes posibilidades de reventarla"</em>.
        </p>
      </header>

      {/* Filtros */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Min señales por país:</label>
        <input
          type="number"
          min={1} max={10} step={1}
          value={minSignals}
          onChange={(e) => setMinSignals(parseInt(e.target.value || "2", 10))}
          style={{
            width: 60, background: "#0F1525", color: "#cbd5e1",
            border: "1px solid #1e293b", borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        />
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Min 👍 por país:</label>
        <input
          type="number"
          min={0} max={10} step={1}
          value={minFeedback}
          onChange={(e) => setMinFeedback(parseInt(e.target.value || "1", 10))}
          style={{
            width: 60, background: "#0F1525", color: "#cbd5e1",
            border: "1px solid #1e293b", borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        />
        <button
          onClick={refresh}
          style={{
            padding: "6px 14px", background: "transparent",
            color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 13,
            cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
        <span style={{ color: "#64748b", fontSize: 11, fontFamily: "monospace", marginLeft: "auto" }}>
          {items.length} oportunidades · {countries.length} países
        </span>
      </section>

      {error && (
        <div style={{ color: "#FF4444", padding: 12, marginBottom: 16, background: "rgba(255,68,68,0.06)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{ color: "#94a3b8", padding: 32, textAlign: "center" }}>Cargando…</div>
      )}

      {!loading && items.length === 0 && (
        <div style={{ padding: 32, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
          🔍 Aún no detectamos oportunidades cross-country. Necesitas:
          <ul style={{ textAlign: "left", maxWidth: 480, margin: "16px auto", color: "#cbd5e1", lineHeight: 1.7 }}>
            <li>≥ {minSignals} señales del mismo país, con la misma idea (cluster)</li>
            <li>≥ {minFeedback} señales con 👍 explícito (validación tuya)</li>
            <li>Esa idea NO debe tener señales en los países objetivo</li>
          </ul>
          <p style={{ marginTop: 12 }}>
            Marca 👍 en señales prometedoras en <a href="/cazar/senales" style={{ color: "#00D4FF" }}>/cazar/senales</a> y vuelve a refrescar.
          </p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <>
          {/* Matriz países × ideas */}
          <div
            style={{
              border: "1px solid #1e293b", borderRadius: 12, overflow: "hidden",
              background: "#0F1525", marginBottom: 24,
            }}
          >
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "#0B0F1A" }}>
                    <th style={{ padding: "10px 12px", textAlign: "left", color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, fontSize: 10, minWidth: 280 }}>
                      Idea / Cluster
                    </th>
                    <th style={{ padding: "10px 8px", textAlign: "center", color: "#94a3b8", fontWeight: 600, fontSize: 10, textTransform: "uppercase" }}>
                      Score
                    </th>
                    {countries.map((c) => (
                      <th key={c} style={{
                        padding: "10px 6px", textAlign: "center", color: "#94a3b8",
                        fontWeight: 600, fontSize: 10, textTransform: "uppercase",
                        writingMode: "vertical-rl", transform: "rotate(180deg)",
                        height: 80, minWidth: 28,
                      }}>
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, idx) => {
                    const valByCountry: Record<string, CountryValidation> = {};
                    it.validated_in.forEach((v) => { valByCountry[v.country] = v; });
                    const missingSet = new Set(it.missing_in);
                    return (
                      <tr key={idx} style={{ borderTop: "1px solid #1e293b" }}>
                        <td style={{ padding: "10px 12px", color: "#cbd5e1", maxWidth: 320 }}>
                          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 2 }}>
                            {it.idea_summary}
                          </div>
                          <div style={{ color: "#64748b", fontSize: 10 }}>
                            {it.cluster_size} señales en el cluster
                          </div>
                        </td>
                        <td style={{ padding: "10px 8px", textAlign: "center" }}>
                          <span style={{
                            color: it.opportunity_score >= 0.7 ? "#00E5A0" : it.opportunity_score >= 0.4 ? "#FFB800" : "#94a3b8",
                            fontWeight: 700, fontFamily: "monospace",
                          }}>
                            {(it.opportunity_score * 100).toFixed(0)}
                          </span>
                        </td>
                        {countries.map((c) => {
                          const v = valByCountry[c];
                          const isMissing = missingSet.has(c);
                          let bg = "transparent", title = "Sin data", content = "·";
                          if (v) {
                            bg = "rgba(0,229,160,0.18)";
                            title = `✓ Validada en ${c}: ${v.signals} señales · 👍 ${v.ups} · 👎 ${v.downs}`;
                            content = String(v.signals);
                          } else if (isMissing) {
                            bg = "rgba(255,68,68,0.15)";
                            title = `🚀 FIRST-MOVER en ${c}: ningún signal todavía`;
                            content = "✱";
                          }
                          return (
                            <td
                              key={c}
                              title={title}
                              style={{
                                padding: "10px 4px", textAlign: "center",
                                background: bg, fontSize: 12, fontWeight: 700,
                                color: v ? "#00E5A0" : isMissing ? "#FF4444" : "#475569",
                                fontFamily: "monospace",
                              }}
                            >
                              {content}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Leyenda */}
            <div style={{ padding: "10px 12px", borderTop: "1px solid #1e293b", display: "flex", gap: 14, fontSize: 11, color: "#94a3b8", flexWrap: "wrap" }}>
              <span><span style={{ background: "rgba(0,229,160,0.18)", color: "#00E5A0", padding: "2px 8px", borderRadius: 3, fontWeight: 700, marginRight: 4 }}>3</span> = nº de señales validadas</span>
              <span><span style={{ background: "rgba(255,68,68,0.15)", color: "#FF4444", padding: "2px 8px", borderRadius: 3, fontWeight: 700, marginRight: 4 }}>✱</span> = first-mover gap (oportunidad)</span>
              <span><span style={{ color: "#475569", padding: "2px 8px" }}>·</span> = sin data</span>
              <span style={{ marginLeft: "auto" }}>Score = (#países validados × 0.3) + (#👍 × 0.2) + (#gaps × 0.05)</span>
            </div>
          </div>

          {/* Detalle de la oportunidad top */}
          {items[0] && (
            <div style={{ background: "#0F1525", border: "1px solid rgba(0,212,255,0.3)", borderRadius: 12, padding: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <h2 style={{ color: "#00D4FF", fontSize: 14, fontWeight: 700, margin: 0, textTransform: "uppercase", letterSpacing: 0.5 }}>
                  🏆 Top oportunidad
                </h2>
                <button
                  onClick={() => analyze(0, items[0])}
                  disabled={analyzing !== null}
                  title="Analiza esta oportunidad con el agente experimental TrendGapAnalyzer (M5.0). Prioriza país + plan de validación. ~$0.008."
                  style={{
                    marginLeft: "auto",
                    padding: "4px 12px",
                    background: "transparent",
                    color: analyzing === 0 ? "#64748b" : "#A78BFA",
                    border: `1px solid ${analyzing === 0 ? "#1e293b" : "#A78BFA"}`,
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: analyzing === 0 ? "wait" : "pointer",
                  }}
                >
                  {analyzing === 0 ? "Analizando…" : analysisByIdx[0] ? "🔄 Re-analizar" : "🤖 Analizar con IA"}
                </button>
              </div>
              <div style={{ color: "#fff", fontSize: 15, fontWeight: 600, marginBottom: 10 }}>
                {items[0].idea_summary}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 6, fontWeight: 600 }}>✓ VALIDADA EN</div>
                  {items[0].validated_in.map((v, i) => (
                    <div key={i} style={{ marginBottom: 6, color: "#cbd5e1", fontSize: 12 }}>
                      <strong style={{ color: "#00E5A0" }}>{v.country}</strong> · {v.signals} señales · 👍 {v.ups} · 👎 {v.downs}
                      {v.sample_themes.slice(0, 1).map((t, j) => (
                        <div key={j} style={{ color: "#64748b", fontSize: 11, fontStyle: "italic", marginLeft: 12, marginTop: 2 }}>
                          ↳ &quot;{t}&quot;
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 6, fontWeight: 600 }}>🚀 FIRST-MOVER GAPS</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {items[0].missing_in.map((c) => (
                      <span key={c} style={{
                        padding: "3px 10px", background: "rgba(255,68,68,0.1)",
                        color: "#FF4444", border: "1px solid rgba(255,68,68,0.4)",
                        borderRadius: 12, fontSize: 11, fontWeight: 600,
                      }}>
                        {c}
                      </span>
                    ))}
                  </div>
                  <div style={{ color: "#64748b", fontSize: 11, marginTop: 10, lineHeight: 1.5 }}>
                    Tip: lanzá una corrida del workflow apuntando a uno de estos países para validar el mercado local antes de invertir.
                  </div>
                </div>
              </div>

              {/* M5.0 — Panel con el análisis del agente TrendGapAnalyzer */}
              {analysisByIdx[0] && (
                <div style={{
                  marginTop: 18,
                  padding: 14,
                  background: "#0B0F1A",
                  border: "1px solid rgba(167,139,250,0.4)",
                  borderRadius: 8,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span style={{
                      color: "#A78BFA", fontSize: 11, fontWeight: 700,
                      textTransform: "uppercase", letterSpacing: 0.5,
                    }}>
                      🤖 Análisis del agente (M5.0 experimental)
                    </span>
                    {analysisByIdx[0].mock_mode && (
                      <span style={{
                        padding: "1px 6px", background: "rgba(255,184,0,0.1)",
                        color: "#FFB800", borderRadius: 3, fontSize: 10, fontWeight: 600,
                      }}>
                        DEMO
                      </span>
                    )}
                    <span style={{
                      marginLeft: "auto", color: "#94a3b8", fontSize: 11,
                      fontFamily: "monospace",
                    }}>
                      confianza {(analysisByIdx[0].confidence * 100).toFixed(0)}%
                    </span>
                  </div>

                  <div style={{ display: "grid", gap: 10 }}>
                    <div>
                      <span style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, marginRight: 6 }}>
                        🎯 ATACAR PRIMERO:
                      </span>
                      <strong style={{ color: "#fff", fontSize: 14 }}>
                        {analysisByIdx[0].priority_country}
                      </strong>
                      <div style={{ color: "#cbd5e1", fontSize: 12, marginTop: 4, lineHeight: 1.5 }}>
                        {analysisByIdx[0].priority_rationale}
                      </div>
                    </div>

                    <div>
                      <span style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, marginRight: 6 }}>
                        ⏱️ TIMING:
                      </span>
                      <span style={{ color: "#cbd5e1", fontSize: 12 }}>
                        {analysisByIdx[0].timing_hypothesis}
                      </span>
                    </div>

                    <div>
                      <span style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, marginRight: 6 }}>
                        📈 PATRÓN DE ADOPCIÓN:
                      </span>
                      <span style={{ color: "#cbd5e1", fontSize: 12 }}>
                        {analysisByIdx[0].adoption_pattern}
                      </span>
                    </div>

                    <div>
                      <div style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
                        🚀 GO-TO-MARKET (validá primero esto):
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, color: "#cbd5e1", fontSize: 12, lineHeight: 1.7 }}>
                        {analysisByIdx[0].go_to_market.map((g, i) => (
                          <li key={i}>{g}</li>
                        ))}
                      </ul>
                    </div>

                    {Object.keys(analysisByIdx[0].risks_per_country).length > 0 && (
                      <div>
                        <div style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
                          ⚠️ RIESGOS POR PAÍS:
                        </div>
                        {Object.entries(analysisByIdx[0].risks_per_country).map(([c, r]) => (
                          <div key={c} style={{ color: "#cbd5e1", fontSize: 12, marginBottom: 3 }}>
                            <strong>{c}:</strong> {r}
                          </div>
                        ))}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 12, color: "#64748b", fontSize: 11, fontFamily: "monospace", paddingTop: 4, borderTop: "1px solid #1e293b" }}>
                      <span>⏳ esfuerzo: {analysisByIdx[0].effort_estimate_weeks}</span>
                      <span>💰 costo análisis: ${analysisByIdx[0].cost_usd_estimated.toFixed(4)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </main>
  );
}
