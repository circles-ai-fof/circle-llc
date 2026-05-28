"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/auth";

type SignalAnalysis = {
  idea_summary: string;       // M3.11
  country_focus: string;      // M3.11
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

// M4.3 — content type → icon + label es
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
  // M4.5 — filtrar por tipo de contenido clasificado (news/blog/producto/...)
  const [contentTypeFilter, setContentTypeFilter] = useState<string>("");
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
  // M4.4 — translation state per signal + toggle "ver original"
  const [translating, setTranslating] = useState<Set<number>>(new Set());
  const [showOriginal, setShowOriginal] = useState<Set<number>>(new Set());

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

  const refresh = async (overrides?: { search?: string }) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: "200",
        min_score: String(minScore),
        sort,
      });
      if (kindFilter) params.set("kind", kindFilter);
      if (contentTypeFilter) params.set("content_type", contentTypeFilter);
      const effectiveSearch = overrides?.search ?? search;
      if (effectiveSearch) params.set("search", effectiveSearch);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minScore, sort, kindFilter, contentTypeFilter]);

  // Debounced search — wait 350ms after the user stops typing
  useEffect(() => {
    const id = setTimeout(() => refresh({ search }), 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

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

  const exportCsv = async () => {
    try {
      const r = await authFetch("/api/v1/signals.csv");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `signals_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const cleanRescan = async () => {
    if (
      !confirm(
        "Re-escaneo limpio: 1) borra mocks viejos, 2) ejecuta scan de todas las fuentes activas, 3) refresca la vista. ¿Continuar?"
      )
    )
      return;
    try {
      // Step 1: cleanup mocks
      const cleanResp = await authFetch("/api/v1/signals/cleanup-mocks", { method: "POST" });
      if (!cleanResp.ok) throw new Error(`Cleanup HTTP ${cleanResp.status}`);
      const cleanData = await cleanResp.json();
      // Step 2: scan all active sources
      const scanResp = await authFetch("/api/v1/sources/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!scanResp.ok) throw new Error(`Scan HTTP ${scanResp.status}`);
      const scanData = await scanResp.json();
      alert(
        `✓ Re-escaneo limpio completo:\n` +
        `• Mocks borrados: ${cleanData.deleted}\n` +
        `• Fuentes escaneadas: ${scanData.scanned_sources}\n` +
        `• Items obtenidos: ${scanData.items_fetched}\n` +
        `• Señales nuevas: ${scanData.signals_created}\n` +
        `• Auto-analizadas: ${scanData.signals_auto_analyzed || 0}`
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
    // M3.13: guard against double-click — each analyze costs ~$0.005 in LLM.
    // The button shows "Analizando…" but a fast double-click could still
    // dispatch a second request before the state updates.
    if (analyzing.has(id)) return;
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
    // M3.13: guard against double-click — batch costs ~$0.05.
    if (batchAnalyzing) return;
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

  const translate = async (id: number) => {
    if (translating.has(id)) return;
    setTranslating((prev) => new Set(prev).add(id));
    try {
      const r = await authFetch(`/api/v1/signals/${id}/translate`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSignals((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, translated_theme: data.translated_theme, translated_excerpt: data.translated_excerpt, language: data.original_language }
            : s
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTranslating((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const toggleOriginal = (id: number) => {
    setShowOriginal((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
    // M3.14: optimistic update — UI cambia AHORA, no espera al backend.
    // Si el server falla, revertimos. Mejora la sensación de instantaneidad
    // sin esperar la latencia de red.
    const newFeedback = fb === "clear" ? null : fb;
    const previous = signals.find((s) => s.id === id)?.feedback ?? null;
    setSignals((prev) =>
      prev.map((s) => (s.id === id ? { ...s, feedback: newFeedback } : s))
    );
    try {
      const r = await authFetch(`/api/v1/signals/${id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: fb }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      // Revert on failure
      setSignals((prev) =>
        prev.map((s) => (s.id === id ? { ...s, feedback: previous } : s))
      );
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const [promoting, setPromoting] = useState<Set<number>>(new Set());
  const promote = async (id: number) => {
    // M3.13: guard against double-click + double charge. Promotion costs ~$0.06.
    if (promoting.has(id)) return;
    if (!confirm("¿Promover esta señal a una corrida completa del workflow? Cuesta ~$0.06.")) return;
    setPromoting((prev) => new Set(prev).add(id));
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
    } finally {
      setPromoting((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // Server now handles score/kind/sort/search. Client-side filter is only
  // for the cheap-but-frequent feedback + trend refinements.
  const visibleSignals = signals.filter((s) => {
    if (feedbackFilter === "none" && s.feedback) return false;
    if (feedbackFilter === "up" && s.feedback !== "up") return false;
    if (feedbackFilter === "down" && s.feedback !== "down") return false;
    if (minTrend > 0 && (s.trend_score || 0) < minTrend) return false;
    return true;
  });

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1200, margin: "0 auto" }}>
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

        {/* M4.5 — filtro por tipo de contenido clasificado */}
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Tipo:</label>
        <select
          value={contentTypeFilter}
          onChange={(e) => setContentTypeFilter(e.target.value)}
          title="Filtra por la clasificación heurística del contenido (noticia/blog/producto/curso/...)"
          style={{
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        >
          <option value="">Todos los tipos</option>
          {Object.entries(CONTENT_TYPE_META).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.icon} {meta.label}
            </option>
          ))}
        </select>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button
            onClick={cleanRescan}
            title="Borra mocks viejos y ejecuta un nuevo scan de todas las fuentes activas. Operación completa en un click."
            style={{
              padding: "6px 14px", background: "rgba(167,139,250,0.08)",
              color: "#A78BFA", border: "1px solid #A78BFA", borderRadius: 6, fontSize: 13,
              cursor: "pointer", fontWeight: 600,
            }}
          >
            🔄 Re-escanear limpio
          </button>
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
            onClick={exportCsv}
            title="Descarga todas las señales como CSV (incluye análisis, fuente, score, trend)."
            style={{
              padding: "6px 14px", background: "transparent",
              color: "#94a3b8", border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
              cursor: "pointer",
            }}
          >
            📊 CSV
          </button>
          <button
            onClick={() => refresh()}
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
        <div
          style={{
            padding: "48px 32px",
            textAlign: "center",
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            marginTop: 8,
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 12 }}>📡</div>
          <h2 style={{ color: "#fff", fontSize: 20, fontWeight: 600, marginBottom: 8 }}>
            No tienes señales todavía
          </h2>
          <p style={{ color: "#94a3b8", fontSize: 14, lineHeight: 1.6, marginBottom: 24, maxWidth: 460, margin: "0 auto 24px" }}>
            El cazador escanea tus fuentes (RSS, Hacker News, Reddit…) y extrae
            ideas relevantes. Empieza añadiendo al menos una fuente y ejecutando
            un escaneo.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <a
              href="/cazar/fuentes"
              style={{
                background: "#00D4FF",
                color: "#0B0F1A",
                padding: "10px 20px",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              📋 Ir a Fuentes
            </a>
            <a
              href="/cazar/bitacora"
              style={{
                background: "transparent",
                color: "#94a3b8",
                padding: "10px 20px",
                border: "1px solid #1e293b",
                borderRadius: 8,
                fontSize: 14,
                textDecoration: "none",
              }}
            >
              📒 Importar archivo (WhatsApp, .txt, .docx)
            </a>
          </div>
          {minScore > 0 && (
            <p style={{ color: "#64748b", fontSize: 12, marginTop: 16 }}>
              Tip: bajar el score mínimo ({minScore.toFixed(1)}) podría mostrar señales que existen pero
              quedaron filtradas.
            </p>
          )}
        </div>
      )}

      {!loading && signals.length > 0 && visibleSignals.length === 0 && (
        <div
          style={{
            padding: "32px 24px",
            textAlign: "center",
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            marginTop: 8,
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 8 }}>🔍</div>
          <p style={{ color: "#cbd5e1", fontSize: 14, marginBottom: 16 }}>
            Tienes <strong>{signals.length}</strong> señal{signals.length === 1 ? "" : "es"}, pero
            ninguna coincide con los filtros actuales.
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
            {search && (
              <button
                onClick={() => setSearch("")}
                style={{
                  padding: "6px 12px", background: "transparent",
                  color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
                }}
              >
                Limpiar búsqueda
              </button>
            )}
            {feedbackFilter !== "all" && (
              <button
                onClick={() => setFeedbackFilter("all")}
                style={{
                  padding: "6px 12px", background: "transparent",
                  color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
                }}
              >
                Quitar filtro feedback
              </button>
            )}
            {minTrend > 0 && (
              <button
                onClick={() => setMinTrend(0)}
                style={{
                  padding: "6px 12px", background: "transparent",
                  color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
                }}
              >
                Quitar trend mín
              </button>
            )}
            {kindFilter && (
              <button
                onClick={() => setKindFilter("")}
                style={{
                  padding: "6px 12px", background: "transparent",
                  color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
                }}
              >
                Mostrar todas las fuentes
              </button>
            )}
            {contentTypeFilter && (
              <button
                onClick={() => setContentTypeFilter("")}
                style={{
                  padding: "6px 12px", background: "transparent",
                  color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 12, cursor: "pointer",
                }}
              >
                Mostrar todos los tipos
              </button>
            )}
          </div>
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
            isTranslating={translating.has(s.id)}
            showOriginal={showOriginal.has(s.id)}
            onAnalyze={() => analyze(s.id)}
            onTranslate={() => translate(s.id)}
            onToggleOriginal={() => toggleOriginal(s.id)}
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
  isTranslating,
  showOriginal,
  onAnalyze,
  onTranslate,
  onToggleOriginal,
  onToggleExpand,
  onFeedback,
  onPromote,
}: {
  signal: Signal;
  isAnalyzing: boolean;
  isExpanded: boolean;
  isTranslating: boolean;
  showOriginal: boolean;
  onAnalyze: () => void;
  onTranslate: () => void;
  onToggleOriginal: () => void;
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
  // M4.4 — translation display logic. We expose these as `effective*` because
  // the JSX below has an IIFE that further refines the theme when it's a
  // generic placeholder ("Mock signal from…"). Translation must be applied
  // FIRST (so the generic check still works after substitution), then the
  // generic→item_title swap is applied as a fallback only when the
  // (possibly-translated) theme is still placeholder-shaped.
  const hasTranslation = !!signal.translated_theme;
  const needsTranslation = signal.language && signal.language !== "es" && signal.language !== "unknown";
  const showingOriginal = hasTranslation && showOriginal;
  const effectiveTheme = hasTranslation && !showOriginal ? signal.translated_theme! : signal.theme;
  const effectiveExcerpt = hasTranslation && !showOriginal ? signal.translated_excerpt! : signal.excerpt;
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
            {/* M4.3 — content type badge — más prominente para visibilidad */}
            {(() => {
              const meta = CONTENT_TYPE_META[signal.content_type] || CONTENT_TYPE_META.unknown;
              return (
                <span
                  title={`Tipo de contenido: ${meta.label}`}
                  style={{
                    padding: "3px 10px",
                    background: `${meta.color}20`,
                    color: meta.color,
                    border: `1px solid ${meta.color}`,
                    borderRadius: 12,
                    fontSize: 12,
                    fontWeight: 700,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span style={{ fontSize: 14 }}>{meta.icon}</span>
                  {meta.label}
                </span>
              );
            })()}
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
          {/* Display title: if theme is a generic placeholder, prefer the
              first item_title — it's much more informative. */}
          {(() => {
            const themeIsGeneric = /^(Mock signal from|Tema recurrente en|Item de|Detected pattern)/i.test(effectiveTheme);
            const firstItemTitle = signal.item_titles?.find((t) => t && t.trim().length > 0);
            const displayTheme =
              themeIsGeneric && firstItemTitle ? firstItemTitle : effectiveTheme;
            const excerptIsGeneric = /^Detected pattern across/i.test(effectiveExcerpt);
            return (
              <>
                <h3 style={{ color: "#fff", fontSize: 17, fontWeight: 600, marginBottom: 8, lineHeight: 1.3 }}>
                  {displayTheme}
                </h3>
                {/* M4.4 — small chip showing translation state next to the title */}
                {hasTranslation && (
                  <div style={{ marginBottom: 8, fontSize: 11, color: "#94a3b8" }}>
                    {showingOriginal ? (
                      <>📘 Mostrando original ({signal.language.toUpperCase()})</>
                    ) : (
                      <>🌐 Traducido del {signal.language.toUpperCase()} al español</>
                    )}
                  </div>
                )}
                {!excerptIsGeneric && (
                  <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.55, marginBottom: 10 }}>
                    {effectiveExcerpt}
                  </p>
                )}
                {/* Items detectados — un bloque limpio en vez de chips repetidos */}
                {signal.evidence_urls.length > 0 && (
                  <div
                    style={{
                      marginBottom: 10,
                      padding: "8px 12px",
                      background: "#0B0F1A",
                      border: "1px solid #1e293b",
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ color: "#94a3b8", fontSize: 10, marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      📰 Artículos detectados ({signal.evidence_urls.length})
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {signal.evidence_urls.slice(0, 3).map((u, i) => {
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
                            title={u}
                            style={{
                              color: "#cbd5e1",
                              fontSize: 12,
                              textDecoration: "none",
                              lineHeight: 1.4,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            <span style={{ color: "#00D4FF", marginRight: 6 }}>→</span>
                            {title ? title : <span style={{ fontFamily: "monospace", fontSize: 11 }}>{host}</span>}
                          </a>
                        );
                      })}
                      {signal.evidence_urls.length > 3 && (
                        <span style={{ color: "#64748b", fontSize: 11, marginTop: 2 }}>
                          + {signal.evidence_urls.length - 3} más en el detalle
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </>
            );
          })()}
          {/* What + country — destacado arriba para que el founder entienda de un vistazo */}
          {hasAnalysis && signal.analysis && (signal.analysis.idea_summary || signal.analysis.country_focus) && (
            <div
              style={{
                marginBottom: 10,
                padding: "10px 12px",
                background: "#0B0F1A",
                border: "1px solid rgba(0,212,255,0.15)",
                borderRadius: 8,
              }}
            >
              {signal.analysis.idea_summary && (
                <div style={{ marginBottom: signal.analysis.country_focus ? 6 : 0 }}>
                  <span style={{ color: "#00D4FF", fontSize: 11, fontWeight: 700, marginRight: 6 }}>
                    💡 QUÉ HACE
                  </span>
                  <span style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5 }}>
                    {signal.analysis.idea_summary}
                  </span>
                </div>
              )}
              {signal.analysis.country_focus && (
                <div>
                  <span style={{ color: "#00D4FF", fontSize: 11, fontWeight: 700, marginRight: 6 }}>
                    🌎 DÓNDE APLICA
                  </span>
                  <span style={{ color: "#cbd5e1", fontSize: 13 }}>
                    {signal.analysis.country_focus}
                  </span>
                </div>
              )}
            </div>
          )}
          {/* Mini-resumen del análisis (si existe) — UNA línea accionable */}
          {hasAnalysis && signal.analysis && !isExpanded && (
            <div
              style={{
                marginBottom: 10,
                padding: "8px 12px",
                background: `${recColor}08`,
                borderLeft: `3px solid ${recColor}`,
                borderRadius: 4,
                fontSize: 12,
                lineHeight: 1.5,
                color: "#cbd5e1",
              }}
            >
              <span style={{ color: recColor, fontWeight: 700 }}>{recLabel}: </span>
              {signal.analysis.reasoning}
            </div>
          )}
          <div style={{ marginTop: 4, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <a
              href={`/cazar/senales/${signal.id}`}
              style={{
                color: "#94a3b8", fontSize: 11, textDecoration: "none",
                borderBottom: "1px dashed #1e293b", paddingBottom: 1,
              }}
            >
              Ver detalle completo →
            </a>
            <CopyPromptButton signal={signal} />
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
          {/* M4.4 — translate to Spanish (Haiku, ~$0.0005). Only show when the
              signal is in a foreign language. If already translated, offer a
              toggle to view the original. */}
          {needsTranslation && !hasTranslation && (
            <button
              onClick={onTranslate}
              disabled={isTranslating}
              title={`Traducir al español (idioma detectado: ${signal.language.toUpperCase()}). Usa Claude Haiku, ~$0.0005.`}
              style={{
                marginTop: 4,
                padding: "6px 12px",
                background: "transparent",
                color: isTranslating ? "#64748b" : "#FFB800",
                border: `1px solid ${isTranslating ? "#1e293b" : "#FFB800"}`,
                borderRadius: 6,
                fontSize: 11,
                cursor: isTranslating ? "wait" : "pointer",
              }}
            >
              {isTranslating ? "Traduciendo…" : `🌐 Traducir (${signal.language.toUpperCase()})`}
            </button>
          )}
          {hasTranslation && (
            <button
              onClick={onToggleOriginal}
              title="Alternar entre versión traducida y original"
              style={{
                marginTop: 4,
                padding: "6px 12px",
                background: "transparent",
                color: "#FFB800",
                border: "1px solid #FFB800",
                borderRadius: 6,
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              {showingOriginal ? "🇪🇸 Ver traducción" : `🌐 Ver original (${signal.language.toUpperCase()})`}
            </button>
          )}
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
            {signal.analysis.idea_summary && (
              <AnalysisCell label="💡 Qué hace la idea" value={signal.analysis.idea_summary} />
            )}
            <AnalysisCell label="🌎 País / región" value={signal.analysis.country_focus || "—"} />
            <AnalysisCell label="📊 Mercado potencial" value={signal.analysis.market_size_estimate} />
            <AnalysisCell label="👤 ICP probable" value={signal.analysis.icp_probable} />
            <AnalysisCell label="⚡ Diferenciador" value={signal.analysis.differentiator} />
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

/**
 * M3.16: botón que copia un prompt listo-para-pegar en ChatGPT/Claude/Gemini.
 * El founder pidió: "necesito un resumen para entender la idea y el nombre
 * de la idea + un prompt de esa idea listo para copiar y llevarlo a una IA".
 *
 * Reutiliza analysis si existe (mercado/ICP/riesgos); si no, usa el theme +
 * excerpt + URLs como insumo. El prompt está en español y pide evaluación
 * estructurada.
 */
function CopyPromptButton({ signal }: { signal: Signal }) {
  const [copied, setCopied] = useState(false);

  const buildPrompt = (): string => {
    const a = signal.analysis;
    const sourceLabel = signal.source_name || signal.source_kind;
    const urls = signal.evidence_urls.slice(0, 5).join("\n  - ");
    let p = `Necesito que evalúes esta idea de negocio y me des recomendaciones específicas.\n\n`;
    p += `**Idea:** ${signal.theme}\n`;
    p += `**Fuente:** ${sourceLabel}\n`;
    if (signal.excerpt) p += `**Contexto:** ${signal.excerpt}\n`;
    if (a) {
      if (a.idea_summary) p += `\n**Qué hace la idea:** ${a.idea_summary}\n`;
      if (a.country_focus) p += `**País / región:** ${a.country_focus}\n`;
      if (a.market_size_estimate) p += `**Mercado estimado:** ${a.market_size_estimate}\n`;
      if (a.icp_probable) p += `**ICP probable:** ${a.icp_probable}\n`;
      if (a.differentiator) p += `**Diferenciador:** ${a.differentiator}\n`;
      if (a.competitors && a.competitors.length) {
        p += `**Competencia:** ${a.competitors.join(", ")}\n`;
      }
      if (a.risks && a.risks.length) {
        p += `**Riesgos:** ${a.risks.join("; ")}\n`;
      }
      if (a.recommendation) {
        p += `**Recomendación previa:** ${a.recommendation} — ${a.reasoning}\n`;
      }
    }
    if (urls) {
      p += `\n**URLs de evidencia:**\n  - ${urls}\n`;
    }
    p += `\n**Lo que necesito de ti:**\n`;
    p += `1. ¿Es una idea viable para LATAM? (1-2 frases)\n`;
    p += `2. ¿Qué ICP específico atacar primero? (rol, tamaño, país)\n`;
    p += `3. ¿Cuál sería el MVP más barato para validarla? (≤2 semanas, ≤$500)\n`;
    p += `4. ¿Cuáles son los 3 mayores riesgos que la matarían?\n`;
    p += `5. ¿Promovería esta idea a una corrida completa del workflow ($0.06)?\n`;
    return p;
  };

  const copy = async () => {
    try {
      const prompt = buildPrompt();
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(prompt);
      } else {
        // Fallback for non-secure contexts
        const ta = document.createElement("textarea");
        ta.value = prompt;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      alert("No se pudo copiar al portapapeles.");
    }
  };

  return (
    <button
      onClick={copy}
      title="Copia un prompt listo para pegar en ChatGPT / Claude / Gemini con toda la info de esta señal"
      style={{
        background: "transparent",
        color: copied ? "#00E5A0" : "#A78BFA",
        border: `1px solid ${copied ? "#00E5A0" : "#A78BFA"}`,
        borderRadius: 6,
        padding: "3px 10px",
        fontSize: 11,
        cursor: "pointer",
        fontWeight: 600,
      }}
    >
      {copied ? "✓ Copiado" : "📋 Copiar prompt IA"}
    </button>
  );
}
