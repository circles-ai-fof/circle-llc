"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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

type SortKey = "recent" | "score" | "trend" | "published";
type FeedbackFilter = "all" | "none" | "up" | "down";

const SOURCE_KINDS: { value: string; label: string }[] = [
  { value: "", label: "Todas las fuentes" },
  { value: "rss", label: "RSS" },
  { value: "hn", label: "Hacker News" },
  { value: "reddit", label: "Reddit" },
  { value: "github_trending", label: "GitHub trending" },
  { value: "product_hunt", label: "Product Hunt" },
  { value: "youtube", label: "YouTube" },
  { value: "bluesky", label: "Bluesky" },
  { value: "telegram", label: "Telegram" },
  { value: "url", label: "URL importada" },
];

export default function SenalesPage() {
  const router = useRouter();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0.5);
  const [sort, setSort] = useState<SortKey>("recent");
  const [kindFilter, setKindFilter] = useState<string>("");
  const [mockMode, setMockMode] = useState<boolean>(false);
  const [promoted, setPromoted] = useState<Signal[]>([]);
  const [showPromoted, setShowPromoted] = useState<boolean>(false);
  // M3.5 — search + advanced filters + per-signal analyze state
  const [search, setSearch] = useState<string>("");
  const [feedbackFilter, setFeedbackFilter] = useState<FeedbackFilter>("all");
  const [minTrend, setMinTrend] = useState<number>(0);
  const [analyzing, setAnalyzing] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [batchAnalyzing, setBatchAnalyzing] = useState<boolean>(false);

  // Detect mock mode (backend running without ANTHROPIC_API_KEY) so we can
  // warn the founder that ideas are placeholders, not real LLM output.
  useEffect(() => {
    (async () => {
      try {
        const r = await authFetch("/api/v1/diagnostic");
        if (r.ok) {
          const d = await r.json();
          setMockMode(d.mode === "mock");
        }
      } catch {
        /* silently ignore — diagnostic is best-effort */
      }
    })();
  }, []);

  // Load the promotion audit log (separate fetch, only when the user opens it)
  const loadPromoted = async () => {
    try {
      const r = await authFetch("/api/v1/signals/promoted?limit=50");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setPromoted((await r.json()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const togglePromoted = async () => {
    if (!showPromoted) await loadPromoted();
    setShowPromoted((v) => !v);
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: "200",
        min_score: String(minScore),
        sort,
      });
      if (kindFilter) params.set("kind", kindFilter);
      const r = await authFetch(`/api/v1/signals?${params.toString()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSignals((await r.json()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [minScore, sort, kindFilter]);

  const cleanup = async () => {
    if (
      !confirm(
        "¿Limpiar señales de más de 30 días que nadie marcó con 👍/👎 ni promovió? Las marcadas se conservan como historial."
      )
    )
      return;
    try {
      const r = await authFetch("/api/v1/signals/cleanup?older_than_days=30", {
        method: "POST",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      alert(
        `✓ Eliminadas ${data.deleted} señales obsoletas.\nConservadas con feedback/promovidas: ${data.survivors_kept_with_feedback}.`
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const cleanupMocks = async () => {
    if (
      !confirm(
        "¿Borrar señales 'Mock signal from rss' viejas que quedaron de pruebas? Estas son placeholders sin contenido real."
      )
    )
      return;
    try {
      const r = await authFetch("/api/v1/signals/cleanup-mocks", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      alert(`✓ ${data.deleted} señales mock eliminadas.`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const analyze = async (id: number) => {
    setAnalyzing((prev) => new Set(prev).add(id));
    try {
      const r = await authFetch(`/api/v1/signals/${id}/analyze`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      // Update the signal in-place with the analysis instead of refetching everything
      setSignals((prev) =>
        prev.map((s) => (s.id === id ? { ...s, analysis: data.analysis } : s))
      );
      setExpanded((prev) => new Set(prev).add(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const analyzeBatch = async () => {
    // Analyze top 10 not-yet-analyzed signals among the visible ones
    const candidateIds = visibleSignals
      .filter((s) => !s.analysis)
      .slice(0, 10)
      .map((s) => s.id);
    if (candidateIds.length === 0) {
      alert("No hay señales pendientes de análisis en la vista actual.");
      return;
    }
    if (
      !confirm(
        `¿Analizar ${candidateIds.length} señales con IdeaAnalyzer? Costo estimado: ~$${(candidateIds.length * 0.005).toFixed(3)}.`
      )
    )
      return;
    setBatchAnalyzing(true);
    try {
      const r = await authFetch("/api/v1/signals/analyze-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_ids: candidateIds }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      alert(
        `✓ Analizadas: ${data.analyzed}\nSaltadas (ya analizadas): ${data.skipped_already_analyzed}\nErrores: ${data.errors}\nCosto: $${data.cost_usd_estimated.toFixed(4)}`
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBatchAnalyzing(false);
    }
  };

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const setFeedback = async (id: number, fb: "up" | "down" | "clear") => {
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

  const promote = async (id: number) => {
    if (!confirm("¿Promover esta señal a una corrida completa del workflow? Cuesta ~$0.06.")) return;
    try {
      const r = await authFetch("/api/v1/gate/run-from-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_id: id }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      alert(`✓ Run ${data.run_id} creado · verdict=${data.verdict}`);
      router.push(`/cazar?run_id=${data.run_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // Client-side filter: search (text), feedback filter, min trend
  // Server still applies score/kind/sort — this is a fast in-browser refine.
  const visibleSignals = signals.filter((s) => {
    if (search) {
      const q = search.toLowerCase();
      const hay = `${s.theme} ${s.excerpt} ${s.suggested_topic} ${s.source_name || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (feedbackFilter === "none" && s.feedback) return false;
    if (feedbackFilter === "up" && s.feedback !== "up") return false;
    if (feedbackFilter === "down" && s.feedback !== "down") return false;
    if (minTrend > 0 && (s.trend_score || 0) < minTrend) return false;
    return true;
  });

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      {/* Mock-mode banner — only shows when backend has no API key configured */}
      {mockMode && (
        <div
          style={{
            background: "rgba(255,184,0,0.08)",
            border: "1px solid rgba(255,184,0,0.4)",
            borderRadius: 8,
            padding: "10px 14px",
            marginBottom: 16,
            color: "#FFB800",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          ⚠️ <strong>Modo demostración activo.</strong> El backend está corriendo
          sin <code style={{ background: "#0B0F1A", padding: "1px 6px", borderRadius: 3 }}>ANTHROPIC_API_KEY</code> —
          las ideas que se generen son <em>placeholders</em> de ejemplo, no
          ideas reales. Configura las API keys del backend para activar el
          workflow real (ver <code>orchestrator/.env.example</code>).
        </div>
      )}

      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          📡 Señales capturadas
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          El cazador extrae estas señales de tus fuentes configuradas. Da 👍 a las
          relevantes, 👎 a las que no, y promueve las prometedoras a una corrida
          completa del workflow.
        </p>
      </header>

      {/* Filter + refresh */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Score mínimo:</label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={minScore}
          onChange={(e) => setMinScore(parseFloat(e.target.value))}
          style={{ width: 160 }}
        />
        <span style={{ color: "#00D4FF", fontSize: 13, fontFamily: "monospace" }}>
          ≥ {minScore.toFixed(1)}
        </span>

        <label style={{ color: "#94a3b8", fontSize: 12, marginLeft: 8 }}>Ordenar:</label>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          style={{
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        >
          <option value="recent">Más recientes</option>
          <option value="score">Mayor score</option>
          <option value="trend">Mayor trend</option>
          <option value="published">Publicación más reciente</option>
        </select>

        <label style={{ color: "#94a3b8", fontSize: 12 }}>Fuente:</label>
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          style={{
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        >
          {SOURCE_KINDS.map((k) => (
            <option key={k.value || "all"} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            onClick={cleanupMocks}
            title="Borra placeholders 'Mock signal from ...' que quedaron de pruebas viejas."
            style={{
              padding: "6px 14px", background: "transparent",
              color: "#94a3b8", border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
              cursor: "pointer",
            }}
          >
            🗑️ Borrar mocks
          </button>
          <button
            onClick={cleanup}
            title="Elimina señales >30 días sin feedback ni promoción. Conserva las marcadas como historial."
            style={{
              padding: "6px 14px", background: "transparent",
              color: "#94a3b8", border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
              cursor: "pointer",
            }}
          >
            🧹 Limpiar viejas
          </button>
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
        </div>
      </section>

      {/* Second row: search + feedback filter + min trend */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="🔍 Buscar en tema, extracto, topic, fuente…"
          style={{
            flex: "1 1 280px",
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "8px 12px", fontSize: 13, outline: "none",
          }}
        />
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Feedback:</label>
        <select
          value={feedbackFilter}
          onChange={(e) => setFeedbackFilter(e.target.value as FeedbackFilter)}
          style={{
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        >
          <option value="all">Todos</option>
          <option value="none">Sin marcar</option>
          <option value="up">👍 Up</option>
          <option value="down">👎 Down</option>
        </select>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Trend mín:</label>
        <input
          type="number"
          min={0}
          max={10}
          step={1}
          value={minTrend}
          onChange={(e) => setMinTrend(parseInt(e.target.value || "0", 10))}
          style={{
            width: 50, background: "#0F1525", color: "#cbd5e1",
            border: "1px solid #1e293b", borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        />
        <button
          onClick={analyzeBatch}
          disabled={batchAnalyzing}
          title="Analiza las primeras 10 señales visibles que aún no tienen análisis. ~$0.005 por señal."
          style={{
            marginLeft: "auto",
            padding: "6px 14px",
            background: "transparent",
            color: batchAnalyzing ? "#64748b" : "#A78BFA",
            border: `1px solid ${batchAnalyzing ? "#1e293b" : "#A78BFA"}`,
            borderRadius: 6,
            fontSize: 12,
            cursor: batchAnalyzing ? "wait" : "pointer",
          }}
        >
          {batchAnalyzing ? "Analizando batch…" : "🤖 Analizar top 10"}
        </button>
        <span style={{ color: "#64748b", fontSize: 11, fontFamily: "monospace" }}>
          {visibleSignals.length}/{signals.length} señales
        </span>
      </section>

      {error && <div style={{ color: "#FF4444", padding: 16, marginBottom: 16 }}>{error}</div>}

      {loading && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>Cargando…</div>
      )}

      {!loading && signals.length === 0 && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>
          No hay señales con score ≥ {minScore.toFixed(1)}. Ve a{" "}
          <a href="/cazar/fuentes" style={{ color: "#00D4FF" }}>Fuentes</a> y
          ejecuta un escaneo.
        </div>
      )}

      {!loading && signals.length > 0 && visibleSignals.length === 0 && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>
          Ninguna señal coincide con los filtros actuales. Prueba con menos restricciones.
        </div>
      )}

      {/* Cards */}
      <div style={{ display: "grid", gap: 12 }}>
        {visibleSignals.map((s) => (
          <SignalCard
            key={s.id}
            signal={s}
            isAnalyzing={analyzing.has(s.id)}
            isExpanded={expanded.has(s.id)}
            onAnalyze={() => analyze(s.id)}
            onToggleExpand={() => toggleExpanded(s.id)}
            onFeedback={(fb) => setFeedback(s.id, fb)}
            onPromote={() => promote(s.id)}
          />
        ))}
      </div>

      {/* Promotion audit log */}
      <section style={{ marginTop: 36 }}>
        <button
          onClick={togglePromoted}
          style={{
            background: "transparent",
            border: "1px solid #1e293b",
            color: "#94a3b8",
            padding: "8px 16px",
            borderRadius: 8,
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          {showPromoted ? "▼" : "▶"} Promociones recientes ({promoted.length || "ver"})
        </button>
        {showPromoted && (
          <div
            style={{
              marginTop: 12,
              border: "1px solid #1e293b",
              borderRadius: 8,
              background: "#0F1525",
              overflow: "hidden",
            }}
          >
            {promoted.length === 0 ? (
              <div style={{ padding: 20, color: "#64748b", fontSize: 13, textAlign: "center" }}>
                Aún no has promovido ninguna señal. Cuando promuevas una, aparecerá aquí con su run_id.
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "#0B0F1A", color: "#94a3b8", textAlign: "left" }}>
                    <th style={{ padding: "10px 12px" }}>Fecha</th>
                    <th style={{ padding: "10px 12px" }}>Fuente</th>
                    <th style={{ padding: "10px 12px" }}>Tema</th>
                    <th style={{ padding: "10px 12px" }}>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {promoted.map((p) => (
                    <tr key={p.id} style={{ borderTop: "1px solid #1e293b" }}>
                      <td style={{ padding: "10px 12px", color: "#cbd5e1", whiteSpace: "nowrap" }}>
                        {new Date(p.created_at * 1000).toLocaleString("es-EC", {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#94a3b8" }}>
                        {p.source_name || p.source_kind}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#cbd5e1" }}>{p.theme}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <a
                          href={`/cazar?run_id=${p.promoted_run_id}`}
                          style={{ color: "#00D4FF", fontFamily: "monospace", fontSize: 11 }}
                        >
                          {p.promoted_run_id?.slice(0, 8)}… →
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function formatRelativeDate(ts: number | null | undefined, prefix: string): string | null {
  if (!ts) return null;
  const now = Date.now() / 1000;
  const diffSec = Math.max(0, now - ts);
  const diffDays = Math.floor(diffSec / 86400);
  const diffHours = Math.floor(diffSec / 3600);
  const diffMin = Math.floor(diffSec / 60);
  if (diffDays >= 1) {
    return `${prefix} hace ${diffDays} ${diffDays === 1 ? "día" : "días"}`;
  }
  if (diffHours >= 1) {
    return `${prefix} hace ${diffHours} ${diffHours === 1 ? "hora" : "horas"}`;
  }
  if (diffMin >= 1) {
    return `${prefix} hace ${diffMin} min`;
  }
  return `${prefix} hace instantes`;
}

function SignalCard({
  signal,
  isAnalyzing,
  isExpanded,
  onAnalyze,
  onToggleExpand,
  onFeedback,
  onPromote,
}: {
  signal: Signal;
  isAnalyzing: boolean;
  isExpanded: boolean;
  onAnalyze: () => void;
  onToggleExpand: () => void;
  onFeedback: (fb: "up" | "down" | "clear") => void;
  onPromote: () => void;
}) {
  const scoreColor =
    signal.score >= 0.8 ? "#00E5A0" : signal.score >= 0.6 ? "#FFB800" : "#94a3b8";
  const publishedLabel = formatRelativeDate(signal.published_at, "publicado");
  const capturedLabel = formatRelativeDate(signal.created_at, "capturado");
  const sourceLabel = signal.source_name || `Fuente ${signal.source_kind}`;
  const hasAnalysis = !!signal.analysis;
  // Recommendation badge color: promote=green, wait=yellow, discard=red
  const recColor =
    signal.analysis?.recommendation === "promote"
      ? "#00E5A0"
      : signal.analysis?.recommendation === "wait_for_more_data"
        ? "#FFB800"
        : signal.analysis?.recommendation === "discard"
          ? "#FF4444"
          : "#94a3b8";
  const recLabel =
    signal.analysis?.recommendation === "promote"
      ? "🟢 PROMOVER"
      : signal.analysis?.recommendation === "wait_for_more_data"
        ? "🟡 ESPERAR"
        : signal.analysis?.recommendation === "discard"
          ? "🔴 DESCARTAR"
          : "";
  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Source line — prominent */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <span style={{ color: "#00D4FF", fontSize: 12, fontWeight: 600 }}>
              📡 {sourceLabel}
            </span>
            <span style={{
              padding: "1px 6px", background: "rgba(0,212,255,0.1)",
              color: "#00D4FF", borderRadius: 3, fontSize: 9, fontFamily: "monospace", textTransform: "uppercase",
            }}>
              {signal.source_kind}
            </span>
          </div>
          {/* Badges row */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <span style={{ color: scoreColor, fontSize: 13, fontWeight: 700, fontFamily: "monospace" }}>
              score {signal.score.toFixed(2)}
            </span>
            {signal.trend_score >= 1 && (
              <span style={{
                padding: "2px 8px", background: "rgba(255,184,0,0.1)",
                color: "#FFB800", borderRadius: 4, fontSize: 11, fontFamily: "monospace", fontWeight: 700,
              }}
              title={`Tema reaparece ${signal.trend_score} ${signal.trend_score === 1 ? 'vez' : 'veces'} en últimos 7 días`}
              >
                🔥 trend +{signal.trend_score.toFixed(0)}
              </span>
            )}
            {publishedLabel && (
              <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: "monospace" }} title="Fecha de publicación original del contenido">
                🗓️ {publishedLabel}
              </span>
            )}
            {!publishedLabel && capturedLabel && (
              <span style={{ color: "#64748b", fontSize: 11, fontFamily: "monospace" }} title="Fecha en la que el cazador capturó la señal">
                ⚲ {capturedLabel}
              </span>
            )}
            {signal.promoted_run_id && (
              <span style={{
                padding: "2px 8px", background: "rgba(0,229,160,0.1)",
                color: "#00E5A0", borderRadius: 4, fontSize: 10, textTransform: "uppercase",
              }}>
                ✓ Promovida
              </span>
            )}
            {hasAnalysis && (
              <span
                style={{
                  padding: "2px 8px",
                  background: `${recColor}20`,
                  color: recColor,
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                onClick={onToggleExpand}
                title="Click para ver el análisis completo"
              >
                {recLabel}
              </span>
            )}
          </div>
          <h3 style={{ color: "#fff", fontSize: 17, fontWeight: 600, marginBottom: 8, lineHeight: 1.3 }}>{signal.theme}</h3>
          <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.55, marginBottom: 8 }}>{signal.excerpt}</p>
          {signal.suggested_topic && (
            <div style={{
              marginTop: 8, padding: 10, background: "#0B0F1A",
              border: "1px solid #1e293b", borderRadius: 6, color: "#94a3b8", fontSize: 12,
            }}>
              <strong style={{ color: "#cbd5e1" }}>Topic sugerido:</strong> {signal.suggested_topic}
            </div>
          )}
          {signal.evidence_urls.length > 0 && (
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {signal.evidence_urls.map((u, i) => {
                const title = signal.item_titles?.[i] || "";
                let host = u;
                try {
                  host = new URL(u).hostname;
                } catch {
                  /* keep raw */
                }
                return (
                  <a
                    key={i}
                    href={u}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={title ? `${title}\n${u}` : u}
                    style={{
                      color: "#00D4FF", fontSize: 11, padding: "2px 8px",
                      background: "rgba(0,212,255,0.05)", borderRadius: 4,
                      textDecoration: "none", fontFamily: "monospace",
                      maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {title ? `📄 ${title.slice(0, 50)}${title.length > 50 ? "…" : ""}` : host}
                  </a>
                );
              })}
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            <a
              href={`/cazar/senales/${signal.id}`}
              style={{
                color: "#94a3b8", fontSize: 11, textDecoration: "none",
                borderBottom: "1px dashed #1e293b", paddingBottom: 1,
              }}
            >
              Ver detalle completo →
            </a>
          </div>
        </div>
        {/* Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 100 }}>
          <button
            onClick={() => onFeedback("up")}
            style={{
              padding: "6px 12px",
              background: signal.feedback === "up" ? "#00E5A0" : "transparent",
              color: signal.feedback === "up" ? "#0B0F1A" : "#00E5A0",
              border: "1px solid #00E5A0", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            👍 Up
          </button>
          <button
            onClick={() => onFeedback("down")}
            style={{
              padding: "6px 12px",
              background: signal.feedback === "down" ? "#FF4444" : "transparent",
              color: signal.feedback === "down" ? "#fff" : "#FF4444",
              border: "1px solid #FF4444", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            👎 Down
          </button>
          {signal.feedback && (
            <button
              onClick={() => onFeedback("clear")}
              style={{
                padding: "4px 10px", background: "transparent", color: "#64748b",
                border: "1px solid #1e293b", borderRadius: 6, fontSize: 11, cursor: "pointer",
              }}
            >
              Limpiar
            </button>
          )}
          <button
            onClick={onPromote}
            disabled={!!signal.promoted_run_id}
            title={
              signal.promoted_run_id
                ? "Esta señal ya generó una corrida"
                : "Promueve esta señal a una corrida completa del workflow. Se envía un prompt potenciado al cazador con: tema, fuente, fecha de publicación, score, trend y resumen."
            }
            style={{
              marginTop: 4, padding: "8px 12px",
              background: signal.promoted_run_id ? "#1e293b" : "#00D4FF",
              color: signal.promoted_run_id ? "#64748b" : "#0B0F1A",
              border: "none", borderRadius: 6, fontSize: 12, fontWeight: 700,
              cursor: signal.promoted_run_id ? "not-allowed" : "pointer",
            }}
          >
            {signal.promoted_run_id ? "Ya promovida" : "→ Promover a idea"}
          </button>
          {!signal.promoted_run_id && (
            <span style={{ color: "#64748b", fontSize: 9, textAlign: "center", lineHeight: 1.3 }}>
              con prompt potenciado
            </span>
          )}
          <button
            onClick={hasAnalysis ? onToggleExpand : onAnalyze}
            disabled={isAnalyzing}
            title={
              hasAnalysis
                ? "Ver/ocultar análisis de mercado"
                : "Analiza esta señal con IA: mercado, ICP, competidores, recomendación. ~$0.005"
            }
            style={{
              marginTop: 4,
              padding: "6px 12px",
              background: "transparent",
              color: isAnalyzing ? "#64748b" : "#A78BFA",
              border: `1px solid ${isAnalyzing ? "#1e293b" : "#A78BFA"}`,
              borderRadius: 6,
              fontSize: 11,
              cursor: isAnalyzing ? "wait" : "pointer",
            }}
          >
            {isAnalyzing
              ? "Analizando…"
              : hasAnalysis
                ? isExpanded
                  ? "▲ Ocultar análisis"
                  : "▼ Ver análisis"
                : "🤖 Analizar"}
          </button>
        </div>
      </div>

      {/* Expandable analysis panel — only when analysis exists and is expanded */}
      {hasAnalysis && isExpanded && signal.analysis && (
        <div
          style={{
            marginTop: 14,
            padding: 14,
            background: "#0B0F1A",
            border: `1px solid ${recColor}40`,
            borderRadius: 8,
          }}
        >
          {/* Recommendation banner */}
          <div
            style={{
              padding: "10px 12px",
              background: `${recColor}10`,
              borderLeft: `3px solid ${recColor}`,
              borderRadius: 4,
              marginBottom: 12,
            }}
          >
            <div style={{ color: recColor, fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
              {recLabel}
            </div>
            <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5 }}>
              {signal.analysis.reasoning}
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 12,
            }}
          >
            <AnalysisCell label="🌎 Mercado potencial" value={signal.analysis.market_size_estimate} />
            <AnalysisCell label="👤 ICP probable" value={signal.analysis.icp_probable} />
            <AnalysisCell label="💡 Diferenciador" value={signal.analysis.differentiator} />
            <AnalysisCell
              label="⚔️ Competencia conocida"
              value={
                signal.analysis.competitors.length > 0
                  ? signal.analysis.competitors.join(" · ")
                  : "—"
              }
            />
          </div>

          {signal.analysis.risks.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 6, fontWeight: 600 }}>
                ⚠️ Riesgos a vigilar
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, color: "#cbd5e1", fontSize: 12, lineHeight: 1.6 }}>
                {signal.analysis.risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AnalysisCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 4, fontWeight: 600 }}>{label}</div>
      <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5 }}>{value || "—"}</div>
    </div>
  );
}
