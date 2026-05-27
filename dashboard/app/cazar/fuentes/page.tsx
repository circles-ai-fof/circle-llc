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
};

const KIND_NEEDS_TARGET = new Set(["url", "rss", "reddit", "youtube", "bluesky", "telegram"]);

const KIND_PLACEHOLDERS: Record<string, string> = {
  url: "https://artículo.com/post",
  rss: "https://blog.com/feed.xml",
  reddit: "startups (sin r/)",
  youtube: "@MrBeast  o  /channel/UCxxxxx",
  bluesky: 'fintech LATAM  o  from:handle.bsky.social',
  telegram: "channelhandle (sin @ ni t.me/)",
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
  }, []);

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
          {loading ? "Cargando…" : `${sources.length} fuente${sources.length === 1 ? "" : "s"}`}
        </div>
        {sources.length === 0 && !loading && (
          <div style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
            No tienes fuentes configuradas. Añade una arriba.
          </div>
        )}
        {sources.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <Th>Nombre</Th>
                <Th>Tipo</Th>
                <Th>Target</Th>
                <Th>Último scan</Th>
                <Th>Calidad</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => {
                const q = quality[s.id];
                return (
                <tr key={s.id} style={{ borderBottom: "1px solid #1e293b" }}>
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
      setResult(
        `✓ ${d.urls_found} URLs encontradas · ${d.sources_created} fuentes nuevas creadas · ${d.skipped_duplicates} duplicadas omitidas`,
      );
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
        <div style={{ color: "#00E5A0", fontSize: 13, marginTop: 10 }}>{result}</div>
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
