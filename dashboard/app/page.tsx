"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";
import StatsBar from "@/components/StatsBar";
import VerdictBadge from "@/components/VerdictBadge";
import RunForm from "@/components/RunForm";

/**
 * M4.10 — Overview ejecutivo con datos REALES del API.
 *
 * Pega los endpoints:
 *  - GET /api/v1/stats               (KPI cards)
 *  - GET /api/v1/runs?limit=20       (tabla de runs recientes)
 *  - GET /api/v1/signals/stats-by-type (mini distribución por tipo)
 *
 * Si el API falla, mostramos un banner amigable y un fallback de "0 runs".
 * Todos los datos vienen del backend. mockData.ts eliminado en M7.8.
 */

type Stats = {
  signals_total: number;
  signals_new_24h: number;
  signals_unmarked: number;
  signals_with_analysis: number;
  signals_promoted: number;
  sources_total: number;
  sources_active: number;
  runs_total: number;
  runs_pending_review: number;
  runs_pass: number;
  runs_kill: number;
  runs_iterate: number;
  cost_usd_total_30d: number;
  cost_usd_total_all_time: number;
};

type RunItem = {
  run_id: string;
  idea_title: string;
  verdict: "pass" | "kill" | "iterate" | "unknown";
  confidence: number;
  landing_slug: string;
  cost_usd_estimated: number;
  needs_human_review: boolean;
  created_at: number;
};

type TypeStats = Record<string, number>;

function formatRelativeDate(ts: number): string {
  if (!ts) return "—";
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return "ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86400)} d`;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [typeStats, setTypeStats] = useState<TypeStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rStats, rRuns, rTypes] = await Promise.all([
        authFetch("/api/v1/stats"),
        authFetch("/api/v1/runs?limit=20"),
        authFetch("/api/v1/signals/stats-by-type"),
      ]);
      if (rStats.ok) setStats(await rStats.json());
      if (rRuns.ok) setRuns((await rRuns.json()).items);
      if (rTypes.ok) setTypeStats(await rTypes.json());
      if (!rStats.ok) throw new Error(`stats HTTP ${rStats.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const passRate = stats && stats.runs_total > 0
    ? Math.round((stats.runs_pass / stats.runs_total) * 100)
    : 0;

  // Derivar la distribución de runs (pass/kill/iterate) para una mini-barra visual
  const totalVerdicts = stats ? stats.runs_pass + stats.runs_kill + stats.runs_iterate : 0;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Overview</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Factory of Factories — EvidenceGateWorkflow
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all hover:brightness-110 active:scale-95"
            style={{ backgroundColor: "transparent", color: "#94a3b8", border: "1px solid #1e293b" }}
          >
            {loading ? "Cargando…" : "↻ Refresh"}
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all hover:brightness-110 active:scale-95"
            style={{ backgroundColor: "#00D4FF", color: "#0B0F1A" }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Nueva fábrica
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="rounded-xl border px-4 py-3 text-sm"
          style={{
            backgroundColor: "rgba(255,68,68,0.06)",
            borderColor: "rgba(255,68,68,0.4)",
            color: "#FF4444",
          }}
        >
          ⚠ No pude leer las estadísticas del backend: <code>{error}</code>. Verificá que esté
          corriendo en <code>http://localhost:8002</code>.
        </div>
      )}

      {/* KPI cards con datos reales del /api/v1/stats */}
      <StatsBar
        total={stats?.runs_total ?? 0}
        passRate={passRate}
        avgConfidence={
          runs.length > 0
            ? (runs.reduce((s, r) => s + r.confidence, 0) / runs.length).toFixed(2)
            : "—"
        }
        totalCost={stats ? stats.cost_usd_total_all_time.toFixed(3) : "0.000"}
      />

      {/* Segunda fila: actividad y estado del cazador */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MiniCard
            icon="📡"
            label="Señales capturadas"
            value={stats.signals_total}
            sub={`${stats.signals_new_24h} nuevas en 24h`}
            href="/cazar/senales"
            accent="#00D4FF"
          />
          <MiniCard
            icon="🚀"
            label="Promovidas a runs"
            value={stats.signals_promoted}
            sub={
              stats.signals_total > 0
                ? `${((stats.signals_promoted / stats.signals_total) * 100).toFixed(1)}% del total`
                : "—"
            }
            href="/cazar/senales"
            accent="#00E5A0"
          />
          <MiniCard
            icon="🎯"
            label="Fuentes activas"
            value={`${stats.sources_active}/${stats.sources_total}`}
            sub={
              stats.signals_unmarked > 0
                ? `${stats.signals_unmarked} señales sin triar`
                : "todas triadas ✓"
            }
            href="/cazar/fuentes"
            accent="#A78BFA"
          />
          <MiniCard
            icon="⚖️"
            label="Pendientes de revisión"
            value={stats.runs_pending_review}
            sub={
              stats.runs_pending_review > 0
                ? "decisión humana necesaria"
                : "todo al día"
            }
            href="/revision"
            accent={stats.runs_pending_review > 0 ? "#FFB800" : "#64748b"}
          />
        </div>
      )}

      {/* Distribución de veredictos — sólo si hay runs */}
      {stats && totalVerdicts > 0 && (
        <div
          className="rounded-xl border p-4"
          style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-300">
              Distribución de veredictos ({totalVerdicts} runs)
            </h2>
            <span className="text-xs text-gray-500">
              Costo últimos 30d: ${stats.cost_usd_total_30d.toFixed(3)}
            </span>
          </div>
          <div className="flex h-3 rounded-full overflow-hidden" style={{ backgroundColor: "#0B0F1A" }}>
            {stats.runs_pass > 0 && (
              <div
                title={`PASS: ${stats.runs_pass}`}
                style={{
                  width: `${(stats.runs_pass / totalVerdicts) * 100}%`,
                  backgroundColor: "#00E5A0",
                }}
              />
            )}
            {stats.runs_iterate > 0 && (
              <div
                title={`ITERATE: ${stats.runs_iterate}`}
                style={{
                  width: `${(stats.runs_iterate / totalVerdicts) * 100}%`,
                  backgroundColor: "#FFB800",
                }}
              />
            )}
            {stats.runs_kill > 0 && (
              <div
                title={`KILL: ${stats.runs_kill}`}
                style={{
                  width: `${(stats.runs_kill / totalVerdicts) * 100}%`,
                  backgroundColor: "#FF4444",
                }}
              />
            )}
          </div>
          <div className="flex gap-4 mt-2 text-xs">
            <span style={{ color: "#00E5A0" }}>● PASS {stats.runs_pass}</span>
            <span style={{ color: "#FFB800" }}>● ITERATE {stats.runs_iterate}</span>
            <span style={{ color: "#FF4444" }}>● KILL {stats.runs_kill}</span>
          </div>
        </div>
      )}

      {/* Mini distribución de señales por tipo */}
      {typeStats && (typeStats.total ?? 0) > 0 && (
        <div
          className="rounded-xl border p-4"
          style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-300">
              Señales por tipo ({typeStats.total} total)
            </h2>
            <a href="/cazar/senales" className="text-xs" style={{ color: "#00D4FF" }}>
              ver detalle →
            </a>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { k: "news", label: "📰 Noticia", color: "#FFB800" },
              { k: "blog", label: "📝 Blog", color: "#A78BFA" },
              { k: "research_paper", label: "🔬 Estudio", color: "#00D4FF" },
              { k: "tool_product", label: "🛠️ Producto", color: "#00E5A0" },
              { k: "course_tutorial", label: "🎓 Curso", color: "#FFB800" },
              { k: "video_podcast", label: "🎙️ Video", color: "#FF8C42" },
              { k: "community", label: "💬 Foro", color: "#A78BFA" },
              { k: "corporate", label: "🏢 Corporativo", color: "#94a3b8" },
              { k: "unknown", label: "❓ Otro", color: "#64748b" },
            ]
              .filter(({ k }) => (typeStats[k] ?? 0) > 0)
              .map(({ k, label, color }) => (
                <a
                  key={k}
                  href={`/cazar/senales`}
                  className="px-3 py-1 rounded-full text-xs font-semibold"
                  style={{
                    background: `${color}10`,
                    color,
                    border: `1px solid ${color}50`,
                    textDecoration: "none",
                  }}
                >
                  {label} {typeStats[k]}
                </a>
              ))}
          </div>
        </div>
      )}

      {/* Tabla de runs recientes (datos REALES) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-200">Runs recientes</h2>
          <span className="text-xs text-gray-500">
            {runs.length} {runs.length === 1 ? "resultado" : "resultados"}
          </span>
        </div>
        {runs.length === 0 && !loading && !error && (
          <div
            className="rounded-xl border p-8 text-center"
            style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
          >
            <div className="text-4xl mb-2">🏭</div>
            <p className="text-gray-300 mb-1">Aún no hay runs ejecutados</p>
            <p className="text-xs text-gray-500 mb-4">
              Cada run cuesta ~$0.06 en LLM y produce un veredicto pass/kill/iterate.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="px-4 py-2 rounded-lg text-sm font-semibold"
              style={{ backgroundColor: "#00D4FF", color: "#0B0F1A" }}
            >
              + Lanzar primera fábrica
            </button>
          </div>
        )}
        {runs.length > 0 && (
          <div
            className="rounded-xl border overflow-hidden"
            style={{ borderColor: "#1E2A3A", backgroundColor: "#111827" }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottomColor: "#1E2A3A", borderBottomWidth: "1px" }}>
                    <Th>Idea</Th>
                    <Th>Veredicto</Th>
                    <Th>Confianza</Th>
                    <Th>Slug</Th>
                    <Th>Costo</Th>
                    <Th>Fecha</Th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {runs.map((r) => (
                    <tr
                      key={r.run_id}
                      className="transition-colors hover:bg-white/[0.02] cursor-pointer"
                      onClick={() => {
                        window.location.href = `/cazar?run_id=${r.run_id}`;
                      }}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-medium text-gray-100">{r.idea_title}</p>
                          <p className="text-xs text-gray-500 font-mono">{r.run_id.slice(0, 8)}…</p>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <VerdictBadge
                          verdict={(r.verdict.toUpperCase() as "PASS" | "KILL" | "ITERATE") || "ITERATE"}
                          size="sm"
                        />
                        {r.needs_human_review && (
                          <span
                            className="ml-2 text-xs px-2 py-0.5 rounded"
                            style={{
                              background: "rgba(255,184,0,0.1)",
                              color: "#FFB800",
                              border: "1px solid #FFB800",
                            }}
                          >
                            ⚖️ revisar
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-16 h-1.5 rounded-full overflow-hidden"
                            style={{ backgroundColor: "#1E2A3A" }}
                          >
                            <div
                              className="h-full rounded-full transition-all"
                              style={{
                                width: `${Math.round(r.confidence * 100)}%`,
                                backgroundColor:
                                  r.confidence >= 0.8
                                    ? "#00E5A0"
                                    : r.confidence >= 0.6
                                      ? "#FFB800"
                                      : "#FF4444",
                              }}
                            />
                          </div>
                          <span className="text-gray-300 font-mono text-xs">
                            {r.confidence.toFixed(2)}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className="font-mono text-xs px-2 py-1 rounded"
                          style={{ backgroundColor: "#1E2A3A", color: "#00D4FF" }}
                        >
                          {r.landing_slug || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-gray-300 font-mono text-xs">
                          ${r.cost_usd_estimated.toFixed(3)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-gray-400 text-xs">
                          {formatRelativeDate(r.created_at)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Modal de nueva fábrica */}
      {showForm && <RunForm onClose={() => setShowForm(false)} />}
    </div>
  );
}

function MiniCard({
  icon, label, value, sub, href, accent,
}: {
  icon: string;
  label: string;
  value: string | number;
  sub?: string;
  href?: string;
  accent: string;
}) {
  const inner = (
    <div
      className="rounded-xl p-4 border h-full transition-all hover:brightness-110"
      style={{
        backgroundColor: "#111827",
        borderColor: "#1E2A3A",
        cursor: href ? "pointer" : "default",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">{icon}</span>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
          {label}
        </p>
      </div>
      <p className="text-2xl font-bold" style={{ color: accent }}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
  return href ? <a href={href} className="block no-underline">{inner}</a> : inner;
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
      {children}
    </th>
  );
}
