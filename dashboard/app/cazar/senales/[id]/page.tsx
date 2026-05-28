"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authFetch } from "@/lib/auth";

type SignalAnalysis = {
  idea_summary: string;
  country_focus: string;
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
  content_type: string;
  // M4.4 — language + on-demand translation
  language: string;
  translated_theme: string | null;
  translated_excerpt: string | null;
  created_at: number;
};

const CONTENT_TYPE_META: Record<string, { icon: string; label: string; color: string }> = {
  news:            { icon: "📰", label: "Noticia",      color: "#FFB800" },
  blog:            { icon: "📝", label: "Blog",         color: "#A78BFA" },
  research_paper:  { icon: "🔬", label: "Estudio",      color: "#00D4FF" },
  tool_product:    { icon: "🛠️", label: "Producto",     color: "#00E5A0" },
  course_tutorial: { icon: "🎓", label: "Curso",        color: "#FFB800" },
  video_podcast:   { icon: "🎙️", label: "Video",        color: "#FF8C42" },
  community:       { icon: "💬", label: "Foro",         color: "#A78BFA" },
  corporate:       { icon: "🏢", label: "Corporativo",  color: "#94a3b8" },
  unknown:         { icon: "❓", label: "Otro",         color: "#64748b" },
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
  // M4.4 — translation state
  const [translating, setTranslating] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);

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

  // M3.17: enriquecer SIN LLM — hace fetch de las URLs y extrae og:title /
  // og:description / <title>, actualizando theme y excerpt con info real.
  // Costo: $0. Útil cuando la señal viene de un chat y el theme es genérico
  // ("Instagram", "Mock signal from rss") porque no sabes de qué trata.
  const [enriching, setEnriching] = useState(false);
  const enrich = async () => {
    if (enriching) return;
    setEnriching(true);
    try {
      const r = await authFetch(`/api/v1/signals/${id}/enrich`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      if (d.urls_fetched === 0) {
        alert(`No se pudo extraer contenido de las URLs (${d.urls_failed} fallaron).`);
      } else {
        alert(
          `✓ Contenido extraído de ${d.urls_fetched} URLs (${d.urls_failed} fallaron).\n` +
          `Theme actualizado: ${d.theme_updated ? "sí" : "no"}\n` +
          `Excerpt actualizado: ${d.excerpt_updated ? "sí" : "no"}`
        );
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setEnriching(false);
    }
  };

  // M4.4 — Traducir al español con Claude Haiku (~$0.0005). Si el idioma ya es
  // español, el backend retorna already_in_spanish=true sin gastar tokens.
  const translate = async () => {
    if (translating) return;
    setTranslating(true);
    try {
      const r = await authFetch(`/api/v1/signals/${id}/translate`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await refresh();
      setShowOriginal(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTranslating(false);
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

  // M4.4 — translation display logic (same as listing page)
  const hasTranslation = !!signal.translated_theme;
  const needsTranslation = signal.language && signal.language !== "es" && signal.language !== "unknown";
  const showingOriginal = hasTranslation && showOriginal;
  const displayTheme = hasTranslation && !showOriginal ? signal.translated_theme! : signal.theme;
  const displayExcerpt = hasTranslation && !showOriginal ? signal.translated_excerpt! : signal.excerpt;

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
            {(() => {
              const meta = CONTENT_TYPE_META[signal.content_type] || CONTENT_TYPE_META.unknown;
              return (
                <span
                  style={{
                    marginLeft: 10,
                    padding: "2px 8px",
                    background: `${meta.color}15`,
                    color: meta.color,
                    border: `1px solid ${meta.color}40`,
                    borderRadius: 4,
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })()}
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
          {displayTheme}
        </h1>
        {hasTranslation && (
          <div style={{ marginBottom: 8, fontSize: 12, color: "#94a3b8" }}>
            {showingOriginal ? (
              <>📘 Mostrando original ({signal.language.toUpperCase()})</>
            ) : (
              <>🌐 Traducido del {signal.language.toUpperCase()} al español</>
            )}
          </div>
        )}
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
          onClick={enrich}
          disabled={enriching}
          title="Hace fetch de las URLs y extrae og:title + og:description. SIN LLM, costo $0. Mejora theme + excerpt con info real de las páginas."
          style={{
            padding: "8px 16px", background: "transparent",
            color: enriching ? "#64748b" : "#00D4FF",
            border: `1px solid ${enriching ? "#1e293b" : "#00D4FF"}`,
            borderRadius: 6, fontSize: 13, cursor: enriching ? "wait" : "pointer",
          }}
        >
          {enriching ? "Extrayendo…" : "🔍 Extraer contenido (gratis)"}
        </button>
        <button
          onClick={reanalyze}
          disabled={analyzing}
          title="Ejecuta IdeaAnalyzer con LLM. Costo ~$0.005."
          style={{
            padding: "8px 16px", background: "transparent",
            color: analyzing ? "#64748b" : "#A78BFA",
            border: `1px solid ${analyzing ? "#1e293b" : "#A78BFA"}`,
            borderRadius: 6, fontSize: 13, cursor: analyzing ? "wait" : "pointer",
          }}
        >
          {analyzing ? "Analizando…" : signal.analysis ? "🔄 Re-analizar" : "🤖 Analizar con IA ($0.005)"}
        </button>
        {/* M4.4 — translate to Spanish. Shown when the signal is in a foreign
            language. If already translated, the same button alternates between
            "ver original" and "ver traducción". */}
        {needsTranslation && !hasTranslation && (
          <button
            onClick={translate}
            disabled={translating}
            title={`Traducir al español (idioma detectado: ${signal.language.toUpperCase()}). Usa Claude Haiku, ~$0.0005.`}
            style={{
              padding: "8px 16px",
              background: "transparent",
              color: translating ? "#64748b" : "#FFB800",
              border: `1px solid ${translating ? "#1e293b" : "#FFB800"}`,
              borderRadius: 6,
              fontSize: 13,
              cursor: translating ? "wait" : "pointer",
            }}
          >
            {translating ? "Traduciendo…" : `🌐 Traducir desde ${signal.language.toUpperCase()}`}
          </button>
        )}
        {hasTranslation && (
          <button
            onClick={() => setShowOriginal((v) => !v)}
            title="Alternar entre versión traducida y original"
            style={{
              padding: "8px 16px",
              background: "transparent",
              color: "#FFB800",
              border: "1px solid #FFB800",
              borderRadius: 6,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            {showingOriginal ? "🇪🇸 Ver traducción" : `🌐 Ver original (${signal.language.toUpperCase()})`}
          </button>
        )}
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

          {/* What + where — prominent at top */}
          {(signal.analysis.idea_summary || signal.analysis.country_focus) && (
            <div
              style={{
                marginBottom: 18,
                padding: 16,
                background: "#0B0F1A",
                border: "1px solid rgba(0,212,255,0.2)",
                borderRadius: 8,
              }}
            >
              {signal.analysis.idea_summary && (
                <div style={{ marginBottom: signal.analysis.country_focus ? 12 : 0 }}>
                  <div style={{ color: "#00D4FF", fontSize: 11, fontWeight: 700, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    💡 Qué hace la idea
                  </div>
                  <div style={{ color: "#fff", fontSize: 15, lineHeight: 1.55 }}>
                    {signal.analysis.idea_summary}
                  </div>
                </div>
              )}
              {signal.analysis.country_focus && (
                <div>
                  <div style={{ color: "#00D4FF", fontSize: 11, fontWeight: 700, marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    🌎 País / región principal
                  </div>
                  <div style={{ color: "#fff", fontSize: 15 }}>
                    {signal.analysis.country_focus}
                  </div>
                </div>
              )}
            </div>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 18,
            }}
          >
            <DetailCell label="📊 Mercado potencial" value={signal.analysis.market_size_estimate} />
            <DetailCell label="👤 ICP probable" value={signal.analysis.icp_probable} />
            <DetailCell label="⚡ Diferenciador" value={signal.analysis.differentiator} />
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
          {displayExcerpt}
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
