"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M4.15 — Niches sub-explorados dentro de mercados gigantes.
 *
 * Inspirado en el audio del founder (29-may): "recoger las migajas de donde
 * están los gigantes — pero recoger migajas es demasiado grande para nuestra
 * realidad".
 *
 * La página agrupa las señales por "parent market" (primera palabra del
 * suggested_topic) y para cada gigante:
 *   - leader_niche: el sub-niche con más señales (donde están todos compitiendo)
 *   - underexplored_niches: sub-niches con ≤ max_niche_size señales (las migajas)
 */

type NicheSub = {
  topic: string;
  signals: number;
  sample_themes: string[];
};

type NicheOpportunity = {
  parent_market: string;
  parent_size: number;
  leader_niche: NicheSub;
  underexplored_niches: NicheSub[];
  opportunity_count: number;
};

// M5.6 — análisis NicheScout (M5.2 agente experimental)
type NicheScoutPlan = {
  target_subniche: string;
  entry_thesis: string;
  competitive_advantage: string;
  minimum_viable_offer: string;
  validation_metrics: string[];
  estimated_capture_pct: string;
  key_risks: string[];
  confidence: number;
  reasoning: string;
  cost_usd_estimated: number;
  mock_mode: boolean;
};

export default function NichosPage() {
  const [items, setItems] = useState<NicheOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minParentSize, setMinParentSize] = useState(5);
  const [maxNicheSize, setMaxNicheSize] = useState(3);
  // M5.6 — NicheScout análisis por card
  const [analyzing, setAnalyzing] = useState<number | null>(null);
  const [plansByIdx, setPlansByIdx] = useState<Record<number, NicheScoutPlan>>({});

  const analyzeNiche = async (idx: number, opp: NicheOpportunity) => {
    if (analyzing !== null) return;
    setAnalyzing(idx);
    try {
      const r = await authFetch("/api/v1/niche-opportunities/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent_market: opp.parent_market,
          parent_size: opp.parent_size,
          leader_niche: opp.leader_niche,
          underexplored_niches: opp.underexplored_niches,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: NicheScoutPlan = await r.json();
      setPlansByIdx((prev) => ({ ...prev, [idx]: data }));
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
        min_parent_size: String(minParentSize),
        max_niche_size: String(maxNicheSize),
        top_parents: "20",
      });
      const r = await authFetch(`/api/v1/niche-opportunities?${params.toString()}`);
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
  }, [minParentSize, maxNicheSize]);

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          🍞 Migajas de gigantes
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14, lineHeight: 1.6, maxWidth: 760 }}>
          Sub-niches <strong>sub-explorados</strong> dentro de mercados padre
          donde ya hay competencia fuerte. Inspirado en el audio del founder:{" "}
          <em>&quot;recoger las migajas de donde están los gigantes&quot;</em>.
          Cada gigante de la lista tiene un líder (donde todos compiten) y
          varias migajas (donde podrías llegar con poca presión competitiva).
        </p>
      </header>

      {/* Filtros */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>
          Tamaño mínimo del gigante:
        </label>
        <input
          type="number"
          min={2}
          max={1000}
          step={1}
          value={minParentSize}
          onChange={(e) => setMinParentSize(parseInt(e.target.value || "5", 10))}
          style={{
            width: 70, background: "#0F1525", color: "#cbd5e1",
            border: "1px solid #1e293b", borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        />
        <label style={{ color: "#94a3b8", fontSize: 12 }}>
          Max señales por migaja:
        </label>
        <input
          type="number"
          min={1}
          max={100}
          step={1}
          value={maxNicheSize}
          onChange={(e) => setMaxNicheSize(parseInt(e.target.value || "3", 10))}
          style={{
            width: 70, background: "#0F1525", color: "#cbd5e1",
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
          {items.length} gigantes con migajas
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
        <div style={{ padding: 32, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12, textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🍞</div>
          <p style={{ color: "#cbd5e1", fontSize: 14, marginBottom: 6 }}>
            No detectamos gigantes con migajas todavía.
          </p>
          <p style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.6, maxWidth: 460, margin: "0 auto" }}>
            Necesitamos al menos <strong>{minParentSize} señales</strong> agrupadas en
            el mismo mercado padre, donde al menos uno de los sub-niches tenga
            ≤ {maxNicheSize} señales. Ejecuta más scans en{" "}
            <a href="/cazar/fuentes" style={{ color: "#00D4FF" }}>/cazar/fuentes</a> para acumular volumen.
          </p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div style={{ display: "grid", gap: 14 }}>
          {items.map((g, idx) => (
            <div
              key={idx}
              style={{
                background: "#0F1525",
                border: "1px solid #1e293b",
                borderRadius: 12,
                padding: 18,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 22 }}>🏛️</span>
                <h2 style={{
                  color: "#fff", fontSize: 18, fontWeight: 700,
                  textTransform: "capitalize", margin: 0,
                }}>
                  {g.parent_market}
                </h2>
                <span style={{
                  marginLeft: "auto", color: "#94a3b8", fontSize: 11,
                  fontFamily: "monospace",
                }}>
                  {g.parent_size} señales totales · {g.opportunity_count} migajas
                </span>
                <button
                  onClick={() => analyzeNiche(idx, g)}
                  disabled={analyzing !== null}
                  title="NicheScout (M5.2 experimental): plan de entrada al sub-niche más prometedor. ~$0.008"
                  style={{
                    padding: "4px 12px",
                    background: "transparent",
                    color: analyzing === idx ? "#64748b" : "#A78BFA",
                    border: `1px solid ${analyzing === idx ? "#1e293b" : "#A78BFA"}`,
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: analyzing === idx ? "wait" : "pointer",
                  }}
                >
                  {analyzing === idx ? "Analizando…" : plansByIdx[idx] ? "🔄 Re-analizar" : "🤖 Analizar con IA"}
                </button>
              </div>

              {/* M5.6 — Panel NicheScout cuando hay análisis */}
              {plansByIdx[idx] && (
                <div style={{
                  marginBottom: 14,
                  padding: 12,
                  background: "#0B0F1A",
                  border: "1px solid rgba(167,139,250,0.4)",
                  borderRadius: 8,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span style={{ color: "#A78BFA", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      🤖 Plan de entrada (NicheScout M5.2)
                    </span>
                    {plansByIdx[idx].mock_mode && (
                      <span style={{ padding: "1px 6px", background: "rgba(255,184,0,0.1)", color: "#FFB800", borderRadius: 3, fontSize: 9, fontWeight: 600 }}>
                        DEMO
                      </span>
                    )}
                    <span style={{ marginLeft: "auto", color: "#94a3b8", fontSize: 10, fontFamily: "monospace" }}>
                      confianza {(plansByIdx[idx].confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ display: "grid", gap: 8, fontSize: 12, lineHeight: 1.5 }}>
                    <div>
                      <span style={{ color: "#A78BFA", fontWeight: 700, marginRight: 6 }}>🎯 SUB-NICHE A ATACAR:</span>
                      <strong style={{ color: "#fff" }}>{plansByIdx[idx].target_subniche}</strong>
                    </div>
                    <div>
                      <span style={{ color: "#A78BFA", fontWeight: 700, marginRight: 6 }}>💡 TESIS:</span>
                      <span style={{ color: "#cbd5e1" }}>{plansByIdx[idx].entry_thesis}</span>
                    </div>
                    <div>
                      <span style={{ color: "#A78BFA", fontWeight: 700, marginRight: 6 }}>⚡ DIFERENCIADOR:</span>
                      <span style={{ color: "#cbd5e1" }}>{plansByIdx[idx].competitive_advantage}</span>
                    </div>
                    <div>
                      <span style={{ color: "#A78BFA", fontWeight: 700, marginRight: 6 }}>🚀 MVP:</span>
                      <span style={{ color: "#cbd5e1" }}>{plansByIdx[idx].minimum_viable_offer}</span>
                    </div>
                    {plansByIdx[idx].validation_metrics.length > 0 && (
                      <div>
                        <div style={{ color: "#A78BFA", fontWeight: 700, marginBottom: 3 }}>📊 MÉTRICAS DE VALIDACIÓN:</div>
                        <ul style={{ margin: 0, paddingLeft: 18, color: "#cbd5e1" }}>
                          {plansByIdx[idx].validation_metrics.map((m, i) => <li key={i}>{m}</li>)}
                        </ul>
                      </div>
                    )}
                    {plansByIdx[idx].key_risks.length > 0 && (
                      <div>
                        <div style={{ color: "#A78BFA", fontWeight: 700, marginBottom: 3 }}>⚠️ RIESGOS:</div>
                        <ul style={{ margin: 0, paddingLeft: 18, color: "#cbd5e1" }}>
                          {plansByIdx[idx].key_risks.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 12, color: "#64748b", fontSize: 10, fontFamily: "monospace", paddingTop: 4, borderTop: "1px solid #1e293b" }}>
                      <span>📈 captura estimada: {plansByIdx[idx].estimated_capture_pct}</span>
                      <span>💰 costo análisis: ${plansByIdx[idx].cost_usd_estimated.toFixed(4)}</span>
                    </div>
                  </div>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                {/* Leader */}
                <div style={{
                  background: "#0B0F1A",
                  border: "1px solid rgba(255,68,68,0.25)",
                  borderRadius: 8,
                  padding: 12,
                }}>
                  <div style={{
                    color: "#FF4444", fontSize: 10, fontWeight: 700,
                    textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6,
                  }}>
                    🥊 Líder del gigante (donde todos compiten)
                  </div>
                  <div style={{ color: "#cbd5e1", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                    {g.leader_niche.topic}
                  </div>
                  <div style={{ color: "#FF4444", fontSize: 11, fontFamily: "monospace", marginBottom: 8 }}>
                    {g.leader_niche.signals} señales · alta competencia
                  </div>
                  <div style={{ color: "#64748b", fontSize: 11, lineHeight: 1.5 }}>
                    {g.leader_niche.sample_themes.slice(0, 2).map((t, i) => (
                      <div key={i} style={{ marginBottom: 2 }}>↳ &quot;{t}&quot;</div>
                    ))}
                  </div>
                </div>

                {/* Underexplored */}
                <div style={{
                  background: "#0B0F1A",
                  border: "1px solid rgba(0,229,160,0.3)",
                  borderRadius: 8,
                  padding: 12,
                }}>
                  <div style={{
                    color: "#00E5A0", fontSize: 10, fontWeight: 700,
                    textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6,
                  }}>
                    🍞 Migajas sub-exploradas ({g.underexplored_niches.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {g.underexplored_niches.map((n, i) => (
                      <div key={i}>
                        <div style={{ color: "#cbd5e1", fontSize: 12, fontWeight: 600 }}>
                          {n.topic}
                        </div>
                        <div style={{ color: "#00E5A0", fontSize: 10, fontFamily: "monospace", marginBottom: 2 }}>
                          {n.signals} señal{n.signals === 1 ? "" : "es"} · baja competencia
                        </div>
                        {n.sample_themes.slice(0, 1).map((t, j) => (
                          <div key={j} style={{ color: "#64748b", fontSize: 11, fontStyle: "italic" }}>
                            ↳ &quot;{t}&quot;
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
