"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type Source = {
  id: number;
  kind: string;
  target: string;
  name: string;
  active: boolean;
  last_scanned_at: number | null;
  created_at: number;
};

const KIND_LABELS: Record<string, string> = {
  url: "URL única",
  rss: "RSS feed",
  hn: "Hacker News",
  reddit: "Reddit",
  github_trending: "GitHub Trending",
  product_hunt: "Product Hunt",
  youtube: "YouTube canal",
  bluesky: "Bluesky (búsqueda)",
  telegram: "Telegram canal público",
  events: "Eventos / Ferias / Congresos (M4.13)",
  sec_edgar: "SEC EDGAR (filings públicas US) (M4.12)",
  google_trends: "Google Trends por país (M4.14)",
};

const KIND_NEEDS_TARGET = new Set(["url", "rss", "reddit", "youtube", "bluesky", "telegram", "events", "sec_edgar", "google_trends"]);

const KIND_PLACEHOLDERS: Record<string, string> = {
  url: "https://artículo.com/post",
  rss: "https://blog.com/feed.xml",
  reddit: "startups (sin r/)",
  youtube: "@MrBeast  o  /channel/UCxxxxx",
  bluesky: 'fintech LATAM  o  from:handle.bsky.social',
  telegram: "channelhandle (sin @ ni t.me/)",
  events: "https://lu.ma/feed.xml  o  https://eventbrite.com/rss/...",
  sec_edgar: "CIK numérico (ej. 320193 = Apple, 789019 = Microsoft)",
  google_trends: "Código de país ISO-2: US, MX, EC, CO, PE, CL, AR, BR, ES, ...",
};

export default function FuentesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [quality, setQuality] = useState<Record<number, {
    quality_score: number;
    signals_total: number;
    signals_up: number;
    signals_down: number;
    signals_promoted: number;
  }>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);

  // Form state
  const [kind, setKind] = useState("rss");
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");

  // M3.16: filters + bulk selection
  const [filterName, setFilterName] = useState("");
  const [filterKind, setFilterKind] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // M4.0: platform detection on URL paste
  type PlatformCheck = {
    platform: string | null;
    status: string;
    needs_credentials: boolean;
    missing_keys: string[];
    oauth_required: boolean;
    message: string;
    recommended_kind: string | null;
  };
  const [platformCheck, setPlatformCheck] = useState<PlatformCheck | null>(null);

  // M4.1: autonomy level + source suggestions
  type Suggestion = {
    cluster_id: number;
    keywords: string[];
    suggested_query: string;
    rationale: string;
  };
  const [autonomyLevel, setAutonomyLevel] = useState<string>("manual");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [reclustering, setReclustering] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rSources, rQuality] = await Promise.all([
        authFetch("/api/v1/sources"),
        authFetch("/api/v1/sources/quality"),
      ]);
      if (!rSources.ok) throw new Error(`HTTP ${rSources.status}`);
      setSources((await rSources.json()).items);
      if (rQuality.ok) {
        type Q = { source_id: number; quality_score: number; signals_total: number; signals_up: number; signals_down: number; signals_promoted: number };
        const q: Q[] = (await rQuality.json()).items;
        const m: Record<number, Q> = {};
        q.forEach((it) => { m[it.source_id] = it; });
        setQuality(m);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // M4.1: load autonomy + suggestions
    (async () => {
      try {
        const [rA, rS] = await Promise.all([
          authFetch("/api/v1/autonomy"),
          authFetch("/api/v1/sources/suggestions"),
        ]);
        if (rA.ok) setAutonomyLevel((await rA.json()).level);
        if (rS.ok) setSuggestions((await rS.json()).items || []);
      } catch {
        /* best-effort */
      }
    })();
  }, []);

  const changeAutonomy = async (level: string) => {
    // M4.5: cambiamos a POST porque PUT requiere que el browser pase un
    // preflight CORS con allow_methods=PUT — y eso requiere reiniciar el
    // backend después del fix CORS. POST siempre estuvo permitido, así que
    // funciona inmediatamente. El backend expone /api/v1/autonomy con ambos
    // verbos (PUT canónico + POST alias). Si el POST falla con 405 (backend
    // muy viejo), reintentamos con PUT como fallback.
    try {
      let r = await authFetch("/api/v1/autonomy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      if (r.status === 405) {
        // backend pre-M4.5 — sólo conoce PUT
        r = await authFetch("/api/v1/autonomy", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ level }),
        });
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setAutonomyLevel(level);
      // Limpiar error previo si lo había
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runRecluster = async () => {
    if (reclustering) return;
    setReclustering(true);
    try {
      const r = await authFetch("/api/v1/preferences/recluster", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      alert(
        `✓ Reclusterización completa.\n` +
        `Modo: ${d.mode}\n` +
        `Señales embedded: ${d.signals_embedded}\n` +
        `Clusters encontrados: ${d.clusters_found}`
      );
      // Reload suggestions
      const rS = await authFetch("/api/v1/sources/suggestions");
      if (rS.ok) setSuggestions((await rS.json()).items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReclustering(false);
    }
  };

  const addFromSuggestion = (s: Suggestion) => {
    // Pre-fill the form with bluesky search + the keywords
    setKind("bluesky");
    setTarget(s.suggested_query);
    setName(`Sugerencia · ${s.keywords.slice(0, 3).join(" + ")}`);
    // Scroll up to form
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // M4.0: debounce check-platform cuando el founder pega/escribe una URL
  useEffect(() => {
    const t = target.trim();
    if (!t || !t.startsWith("http")) {
      setPlatformCheck(null);
      return;
    }
    const handle = setTimeout(async () => {
      try {
        const r = await authFetch("/api/v1/sources/check-platform", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: t }),
        });
        if (!r.ok) return;
        setPlatformCheck(await r.json());
      } catch {
        /* best-effort */
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [target]);

  const addSource = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Nombre requerido");
      return;
    }
    if (KIND_NEEDS_TARGET.has(kind) && !target.trim()) {
      setError(`${KIND_LABELS[kind]} requiere un target (URL o subreddit)`);
      return;
    }
    try {
      const r = await authFetch("/api/v1/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, target: target.trim(), name: name.trim() }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setKind("rss");
      setTarget("");
      setName("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const deleteSource = async (id: number) => {
    if (!confirm("¿Eliminar esta fuente?")) return;
    try {
      await authFetch(`/api/v1/sources/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // M3.16: filtered view of sources for the table + checkboxes
  const filteredSources = sources.filter((s) => {
    if (filterName) {
      const q = filterName.toLowerCase();
      const hay = `${s.name} ${s.target}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filterKind && s.kind !== filterKind) return false;
    return true;
  });

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelected(new Set(filteredSources.map((s) => s.id)));
  };

  const clearSelection = () => setSelected(new Set());

  const bulkDeleteSelected = async () => {
    if (selected.size === 0) return;
    if (bulkDeleting) return;
    if (!confirm(`¿Eliminar ${selected.size} fuente${selected.size === 1 ? "" : "s"} seleccionada${selected.size === 1 ? "" : "s"}? Esta acción no se puede deshacer.`)) return;
    setBulkDeleting(true);
    try {
      const r = await authFetch("/api/v1/sources/bulk-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_ids: Array.from(selected) }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setSelected(new Set());
      await refresh();
      setScanResult(`🗑️ ${d.deleted} fuentes eliminadas`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkDeleting(false);
    }
  };

  const bulkDeleteByTarget = async (substring: string, label: string) => {
    if (bulkDeleting) return;
    if (!confirm(`¿Eliminar TODAS las fuentes que contengan "${substring}" en el target?\n(${label})`)) return;
    setBulkDeleting(true);
    try {
      const r = await authFetch("/api/v1/sources/bulk-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_contains: substring }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      await refresh();
      setScanResult(`🗑️ ${d.deleted} fuentes de "${substring}" eliminadas`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkDeleting(false);
    }
  };

  const scanNow = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const r = await authFetch("/api/v1/sources/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_promote_threshold: 0 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setScanResult(
        `✓ Escaneadas ${data.scanned_sources} fuentes · ${data.items_fetched} items recolectados · ${data.signals_created} señales nuevas`
      );
      await refresh();
    } catch (e) {
      setScanResult(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setScanning(false);
    }
  };

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          🎯 Fuentes del cazador
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Configura RSS feeds, Hacker News, Reddit, GitHub Trending, Product Hunt.
          El cazador escanea estas fuentes y extrae señales que luego puedes
          revisar y convertir en ideas.
        </p>
      </header>

      {/* Add source form */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 20,
          marginBottom: 20,
        }}
      >
        <h3 style={{ color: "#94a3b8", fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 12 }}>
          + Añadir fuente
        </h3>
        <form onSubmit={addSource} style={{ display: "grid", gridTemplateColumns: "180px 1fr 1fr auto", gap: 8, alignItems: "center" }}>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            style={{
              padding: "10px 12px", background: "#0B0F1A", color: "#fff",
              border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
            }}
          >
            {Object.entries(KIND_LABELS).map(([k, lab]) => (
              <option key={k} value={k}>{lab}</option>
            ))}
          </select>
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={KIND_PLACEHOLDERS[kind] || "(no aplica)"}
            disabled={!KIND_NEEDS_TARGET.has(kind)}
            style={{
              padding: "10px 12px", background: "#0B0F1A", color: "#fff",
              border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
              opacity: KIND_NEEDS_TARGET.has(kind) ? 1 : 0.5,
            }}
          />
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre (ej. 'TechCrunch ES')"
            style={{
              padding: "10px 12px", background: "#0B0F1A", color: "#fff",
              border: "1px solid #1e293b", borderRadius: 6, fontSize: 13,
            }}
          />
          <button
            type="submit"
            style={{
              padding: "10px 20px", background: "#00D4FF", color: "#0B0F1A",
              border: "none", borderRadius: 6, fontWeight: 700, fontSize: 13, cursor: "pointer",
            }}
          >
            Añadir
          </button>
        </form>
        {error && <div style={{ color: "#FF4444", fontSize: 12, marginTop: 8 }}>{error}</div>}
        {/* M4.0: platform check banner */}
        {platformCheck && platformCheck.platform && (
          <div
            style={{
              marginTop: 12,
              padding: "10px 14px",
              borderRadius: 8,
              fontSize: 13,
              lineHeight: 1.5,
              background:
                platformCheck.status === "deferred"
                  ? "rgba(255,68,68,0.06)"
                  : platformCheck.status === "configured" || platformCheck.status === "ready"
                  ? "rgba(0,229,160,0.06)"
                  : "rgba(255,184,0,0.06)",
              border: `1px solid ${
                platformCheck.status === "deferred"
                  ? "rgba(255,68,68,0.3)"
                  : platformCheck.status === "configured" || platformCheck.status === "ready"
                  ? "rgba(0,229,160,0.3)"
                  : "rgba(255,184,0,0.3)"
              }`,
              color:
                platformCheck.status === "deferred"
                  ? "#FF4444"
                  : platformCheck.status === "configured" || platformCheck.status === "ready"
                  ? "#00E5A0"
                  : "#FFB800",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4, textTransform: "capitalize" }}>
              Plataforma detectada: {platformCheck.platform}
              {platformCheck.recommended_kind && platformCheck.recommended_kind !== kind && (
                <span style={{ color: "#94a3b8", fontWeight: 400, fontSize: 11, marginLeft: 8 }}>
                  (sugerencia: cambia tipo a "{platformCheck.recommended_kind}")
                </span>
              )}
            </div>
            <div style={{ color: "#cbd5e1" }}>{platformCheck.message}</div>
            {platformCheck.missing_keys.length > 0 && (
              <div style={{ marginTop: 6, color: "#94a3b8", fontSize: 12 }}>
                Variables faltantes en <code style={{ background: "#0B0F1A", padding: "1px 6px", borderRadius: 3 }}>orchestrator/.env</code>:{" "}
                {platformCheck.missing_keys.map((k) => (
                  <code
                    key={k}
                    style={{
                      background: "#0B0F1A",
                      padding: "1px 6px",
                      borderRadius: 3,
                      marginRight: 4,
                      fontSize: 11,
                    }}
                  >
                    {k}
                  </code>
                ))}
              </div>
            )}
            <div style={{ marginTop: 6 }}>
              <a
                href="/configuracion/cuentas"
                style={{ color: "#00D4FF", fontSize: 12, textDecoration: "none" }}
              >
                → Ver estado de todas las plataformas
              </a>
            </div>
          </div>
        )}
      </section>

      {/* M4.1: Autonomy selector + suggestions */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 18,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 280px" }}>
            <div style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
              🧠 Nivel de autonomía del cazador
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {[
                { value: "manual", label: "🛑 Manual", desc: "Tú añades todas las fuentes" },
                { value: "assisted", label: "🧠 Asistido", desc: "El sistema sugiere, tú apruebas" },
                { value: "autonomous_with_approval", label: "🤖 Autónomo", desc: "El sistema añade pendientes de aprobar" },
              ].map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => changeAutonomy(opt.value)}
                  title={opt.desc}
                  style={{
                    padding: "8px 14px",
                    background: autonomyLevel === opt.value ? "rgba(167,139,250,0.15)" : "transparent",
                    color: autonomyLevel === opt.value ? "#A78BFA" : "#94a3b8",
                    border: `1px solid ${autonomyLevel === opt.value ? "#A78BFA" : "#1e293b"}`,
                    borderRadius: 6,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <div style={{ color: "#64748b", fontSize: 11, marginTop: 6 }}>
              {autonomyLevel === "manual" && "El cazador NO sugiere fuentes — tú decides qué monitorear."}
              {autonomyLevel === "assisted" && "El cazador muestra sugerencias basadas en tus 👍 — apruebas o rechazas."}
              {autonomyLevel === "autonomous_with_approval" && "El cazador añade sugerencias automáticamente como pendientes de tu aprobación."}
            </div>
          </div>
          <button
            onClick={runRecluster}
            disabled={reclustering}
            title="Genera embeddings de todas las señales sin uno y reagrupa con clustering. Sin costo LLM."
            style={{
              padding: "8px 14px", background: "transparent",
              color: reclustering ? "#64748b" : "#A78BFA",
              border: `1px solid ${reclustering ? "#1e293b" : "#A78BFA"}`,
              borderRadius: 6, fontSize: 12, cursor: reclustering ? "wait" : "pointer",
            }}
          >
            {reclustering ? "Procesando…" : "🔁 Re-cluster (gratis)"}
          </button>
        </div>

        {/* Sugerencias del cluster */}
        {autonomyLevel !== "manual" && suggestions.length > 0 && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #1e293b" }}>
            <div style={{ color: "#94a3b8", fontSize: 11, fontWeight: 600, textTransform: "uppercase", marginBottom: 8 }}>
              🌱 Sugerencias basadas en tus 👍
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {suggestions.map((s) => (
                <div
                  key={s.cluster_id}
                  style={{
                    padding: "10px 14px",
                    background: "#0B0F1A",
                    border: "1px solid rgba(167,139,250,0.2)",
                    borderRadius: 8,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {s.keywords.slice(0, 5).map((k) => (
                        <code key={k} style={{
                          background: "rgba(167,139,250,0.1)", color: "#A78BFA",
                          padding: "1px 6px", borderRadius: 3, fontSize: 11,
                        }}>{k}</code>
                      ))}
                    </div>
                    <button
                      onClick={() => addFromSuggestion(s)}
                      style={{
                        padding: "4px 10px", background: "#A78BFA", color: "#0B0F1A",
                        border: "none", borderRadius: 4, fontSize: 11, fontWeight: 700, cursor: "pointer",
                      }}
                    >
                      + Crear fuente Bluesky
                    </button>
                  </div>
                  <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5 }}>{s.rationale}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {autonomyLevel !== "manual" && suggestions.length === 0 && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #1e293b", color: "#64748b", fontSize: 12 }}>
            Aún no hay sugerencias. Marca 👍 a 3+ señales similares y ejecuta &quot;🔁 Re-cluster&quot; para que aparezcan.
          </div>
        )}
      </section>

      {/* Scan button */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <button
          onClick={scanNow}
          disabled={scanning || sources.length === 0}
          style={{
            padding: "12px 24px", background: "#00E5A0", color: "#0B0F1A",
            border: "none", borderRadius: 8, fontWeight: 700, fontSize: 14,
            cursor: scanning || sources.length === 0 ? "not-allowed" : "pointer",
            opacity: scanning || sources.length === 0 ? 0.5 : 1,
          }}
        >
          {scanning ? "Escaneando…" : "▶ Escanear ahora"}
        </button>
        {scanResult && <div style={{ color: scanResult.startsWith("✓") ? "#00E5A0" : "#FF4444", fontSize: 13 }}>{scanResult}</div>}
        {sources.length === 0 && (
          <span style={{ color: "#64748b", fontSize: 12 }}>Añade al menos una fuente para escanear</span>
        )}
      </section>

      {/* M3.16: Filters + bulk actions */}
      {sources.length > 0 && (
        <section style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
          <input
            type="search"
            placeholder="🔍 Filtrar por nombre o URL…"
            value={filterName}
            onChange={(e) => setFilterName(e.target.value)}
            style={{
              flex: "1 1 240px",
              background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
              borderRadius: 6, padding: "6px 10px", fontSize: 13, outline: "none",
            }}
          />
          <select
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value)}
            style={{
              background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
              borderRadius: 6, padding: "6px 10px", fontSize: 12,
            }}
          >
            <option value="">Todos los tipos</option>
            <option value="rss">RSS</option>
            <option value="url">URL importada</option>
            <option value="hn">Hacker News</option>
            <option value="reddit">Reddit</option>
            <option value="youtube">YouTube</option>
            <option value="bluesky">Bluesky</option>
            <option value="telegram">Telegram</option>
            <option value="github_trending">GitHub trending</option>
            <option value="product_hunt">Product Hunt</option>
          </select>
          <span style={{ color: "#64748b", fontSize: 12, marginLeft: 4 }}>
            {filteredSources.length}/{sources.length}
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              onClick={() => bulkDeleteByTarget("instagram.com", "Posts/reels de Instagram")}
              title="Borra todas las fuentes que tengan instagram.com en su URL"
              style={{
                padding: "6px 12px", background: "transparent", color: "#FFB800",
                border: "1px solid rgba(255,184,0,0.4)", borderRadius: 6, fontSize: 12, cursor: "pointer",
              }}
            >
              🧹 Borrar Instagram
            </button>
            <button
              onClick={() => bulkDeleteByTarget("x.com", "Status de X/Twitter")}
              style={{
                padding: "6px 12px", background: "transparent", color: "#FFB800",
                border: "1px solid rgba(255,184,0,0.4)", borderRadius: 6, fontSize: 12, cursor: "pointer",
              }}
            >
              🧹 Borrar X.com
            </button>
            <button
              onClick={() => bulkDeleteByTarget("tiktok.com", "Videos de TikTok")}
              style={{
                padding: "6px 12px", background: "transparent", color: "#FFB800",
                border: "1px solid rgba(255,184,0,0.4)", borderRadius: 6, fontSize: 12, cursor: "pointer",
              }}
            >
              🧹 Borrar TikTok
            </button>
          </div>
        </section>
      )}
      {selected.size > 0 && (
        <section
          style={{
            display: "flex", gap: 12, alignItems: "center",
            padding: "8px 14px", marginBottom: 12,
            background: "rgba(255,68,68,0.06)", border: "1px solid rgba(255,68,68,0.3)",
            borderRadius: 8,
          }}
        >
          <span style={{ color: "#FF4444", fontSize: 13, fontWeight: 600 }}>
            {selected.size} seleccionada{selected.size === 1 ? "" : "s"}
          </span>
          <button
            onClick={bulkDeleteSelected}
            disabled={bulkDeleting}
            style={{
              padding: "6px 14px", background: "#FF4444", color: "#fff",
              border: "none", borderRadius: 6, fontSize: 12, fontWeight: 600,
              cursor: bulkDeleting ? "wait" : "pointer",
            }}
          >
            {bulkDeleting ? "Eliminando…" : "🗑️ Eliminar seleccionadas"}
          </button>
          <button
            onClick={clearSelection}
            style={{
              padding: "6px 14px", background: "transparent", color: "#94a3b8",
              border: "1px solid #1e293b", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            Cancelar
          </button>
        </section>
      )}

      {/* Sources table */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        <div style={{ padding: "12px 20px", borderBottom: "1px solid #1e293b", color: "#94a3b8", fontSize: 13 }}>
          {loading
            ? "Cargando…"
            : `${filteredSources.length}${filteredSources.length !== sources.length ? ` de ${sources.length}` : ""} fuente${filteredSources.length === 1 ? "" : "s"}`}
        </div>
        {sources.length === 0 && !loading && (
          <div style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
            No tienes fuentes configuradas. Añade una arriba.
          </div>
        )}
        {sources.length > 0 && filteredSources.length === 0 && (
          <div style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
            Ninguna fuente coincide con el filtro. <button onClick={() => { setFilterName(""); setFilterKind(""); }} style={{ background: "transparent", color: "#00D4FF", border: "none", cursor: "pointer", fontSize: 13 }}>Limpiar filtro</button>
          </div>
        )}
        {filteredSources.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <Th>
                  <input
                    type="checkbox"
                    checked={selected.size === filteredSources.length && filteredSources.length > 0}
                    onChange={(e) => (e.target.checked ? selectAllVisible() : clearSelection())}
                    title="Seleccionar todas las visibles"
                  />
                </Th>
                <Th>Nombre</Th>
                <Th>Tipo</Th>
                <Th>Target</Th>
                <Th>Último scan</Th>
                <Th>Calidad</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {filteredSources.map((s) => {
                const q = quality[s.id];
                const isSelected = selected.has(s.id);
                return (
                <tr
                  key={s.id}
                  style={{
                    borderBottom: "1px solid #1e293b",
                    background: isSelected ? "rgba(255,68,68,0.05)" : undefined,
                  }}
                >
                  <Td>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(s.id)}
                    />
                  </Td>
                  <Td>{s.name}</Td>
                  <Td>
                    <span style={{
                      padding: "2px 8px", background: "rgba(0,212,255,0.1)",
                      color: "#00D4FF", borderRadius: 4, fontSize: 11, fontFamily: "monospace",
                    }}>
                      {KIND_LABELS[s.kind] || s.kind}
                    </span>
                  </Td>
                  <Td mono>{s.target || "—"}</Td>
                  <Td>{s.last_scanned_at ? new Date(s.last_scanned_at * 1000).toLocaleString() : "Nunca"}</Td>
                  <Td>
                    {q ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span style={{
                          color: q.quality_score >= 0.6 ? "#00E5A0" : q.quality_score >= 0.3 ? "#FFB800" : "#FF4444",
                          fontFamily: "monospace", fontSize: 12, fontWeight: 700,
                        }}
                        title={`Calidad: ${(q.quality_score * 100).toFixed(0)}% (combinado de up rate + promoted rate + volumen)`}
                        >
                          {(q.quality_score * 100).toFixed(0)}%
                        </span>
                        <span style={{ color: "#64748b", fontSize: 10, fontFamily: "monospace" }}>
                          {q.signals_total} sigs · 👍{q.signals_up} 👎{q.signals_down} · 🚀{q.signals_promoted}
                        </span>
                      </div>
                    ) : (
                      <span style={{ color: "#64748b", fontSize: 11 }}>sin data</span>
                    )}
                  </Td>
                  <Td>
                    <button
                      onClick={() => deleteSource(s.id)}
                      style={{
                        padding: "4px 10px", background: "transparent", color: "#FF4444",
                        border: "1px solid #FF4444", borderRadius: 4, fontSize: 11, cursor: "pointer",
                      }}
                    >
                      Eliminar
                    </button>
                  </Td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* File import */}
      <FileImportSection onImported={refresh} />

      {/* Cron hint */}
      <section
        style={{
          marginTop: 20, padding: 16, background: "#0F1525",
          border: "1px solid #1e293b", borderRadius: 12, color: "#94a3b8", fontSize: 13,
        }}
      >
        💡 <strong style={{ color: "#fff" }}>Modo automático:</strong> el cron del repo
        (`.github/workflows/auto-scan.yml`) ejecuta este endpoint cada 6h llamando
        a <code style={{ color: "#00D4FF" }}>POST /api/v1/sources/scan</code> con
        <code style={{ color: "#00D4FF" }}> auto_promote_threshold=0.85</code> — los
        signals que superan ese umbral se convierten automáticamente en runs del
        workflow completo.
      </section>
    </main>
  );
}

function FileImportSection({ onImported }: { onImported: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await authFetch("/api/v1/sources/import-file", {
        method: "POST",
        body: fd,
      });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        throw new Error(b.detail || `HTTP ${r.status}`);
      }
      const d = await r.json();
      // M3.15: el filtro de calidad descarta status de X/IG, reels, etc.
      // Mostramos el resumen + qué se descartó con razón para que el founder
      // entienda por qué algunas URLs no se guardaron.
      const noiseCount = d.urls_discarded_as_noise || 0;
      const samples = (d.discarded_samples || []) as { url: string; reason: string }[];
      let msg = `✓ ${d.urls_found} URLs encontradas · ${d.sources_created} fuentes nuevas · ${d.skipped_duplicates} duplicadas`;
      if (noiseCount > 0) {
        msg += `\n🧹 ${noiseCount} descartadas como ruido (status de X/Instagram/llamadas):`;
        for (const s of samples.slice(0, 5)) {
          const shortUrl = s.url.length > 60 ? s.url.slice(0, 57) + "…" : s.url;
          msg += `\n  • ${shortUrl} → ${s.reason}`;
        }
        if (samples.length > 5) {
          msg += `\n  …y ${samples.length - 5} más`;
        }
      }
      setResult(msg);
      onImported();
    } catch (e2) {
      setError(e2 instanceof Error ? e2.message : String(e2));
    } finally {
      setUploading(false);
      e.target.value = ""; // allow re-upload of same file
    }
  };

  return (
    <section
      style={{
        marginTop: 20,
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: 20,
      }}
    >
      <h3 style={{ color: "#94a3b8", fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 4 }}>
        📥 Importar archivo de chat / notas
      </h3>
      <p style={{ color: "#64748b", fontSize: 12, marginBottom: 12 }}>
        Sube un export de WhatsApp (.txt), notas en texto plano (.txt/.csv) o Word (.docx).
        Extraemos los URLs y los registramos en la <a href="/cazar/bitacora" style={{ color: "#00D4FF" }}>bitácora</a> + los agregamos como fuentes.
        Después puedes analizarlos con LLM (resumen, sector, área) o descartar los irrelevantes.
      </p>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="file"
          accept=".txt,.csv,.docx"
          onChange={handleFile}
          disabled={uploading}
          style={{
            color: "#94a3b8",
            fontSize: 13,
            cursor: uploading ? "wait" : "pointer",
          }}
        />
        {uploading && <span style={{ color: "#00D4FF", fontSize: 12 }}>Procesando…</span>}
      </div>
      {result && (
        <div
          style={{
            color: "#00E5A0",
            fontSize: 13,
            marginTop: 10,
            whiteSpace: "pre-line",
            lineHeight: 1.55,
            background: "#0B0F1A",
            padding: "10px 12px",
            borderRadius: 6,
            border: "1px solid rgba(0,229,160,0.2)",
          }}
        >
          {result}
        </div>
      )}
      {error && (
        <div style={{ color: "#FF4444", fontSize: 13, marginTop: 10 }}>✗ {error}</div>
      )}
    </section>
  );
}


function Th({ children = null }: { children?: React.ReactNode }) {
  return (
    <th style={{ textAlign: "left", padding: "10px 16px", color: "#94a3b8", fontSize: 11, fontWeight: 500, letterSpacing: 0.5, textTransform: "uppercase" }}>
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td style={{ padding: "10px 16px", color: "#cbd5e1", fontSize: 13, fontFamily: mono ? "monospace" : "inherit" }}>
      {children}
    </td>
  );
}
