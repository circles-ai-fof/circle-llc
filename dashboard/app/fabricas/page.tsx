"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/auth";
import VerdictBadge from "@/components/VerdictBadge";

/**
 * M7.0 — Cleanup pass: esta página ahora consume el endpoint real
 * /api/v1/runs en vez del legacy mockRuns.
 */

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

type VerdictFilter = "ALL" | "PASS" | "KILL" | "ITERATE";

export default function FabricasPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<VerdictFilter>("ALL");

  useEffect(() => {
    (async () => {
      try {
        const r = await authFetch("/api/v1/runs?limit=100");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setRuns(data.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = filter === "ALL"
    ? runs
    : runs.filter((r) => r.verdict.toUpperCase() === filter);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">Fábricas</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Todas las corridas del EvidenceGateWorkflow ({runs.length} totales)
        </p>
      </div>

      {loading && <p className="text-gray-400 p-6 text-center">Cargando…</p>}
      {error && (
        <div className="rounded-xl border p-4" style={{ backgroundColor: "rgba(255,68,68,0.06)", borderColor: "rgba(255,68,68,0.4)", color: "#FF4444" }}>
          ⚠ {error}
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="flex gap-2 flex-wrap">
            {(["ALL", "PASS", "ITERATE", "KILL"] as VerdictFilter[]).map((v) => {
              const count = v === "ALL" ? runs.length : runs.filter((r) => r.verdict.toUpperCase() === v).length;
              const isActive = filter === v;
              return (
                <button
                  key={v}
                  onClick={() => setFilter(v)}
                  className="px-3 py-2 rounded-lg text-sm font-semibold transition-colors"
                  style={{
                    backgroundColor: isActive ? "rgba(0, 212, 255, 0.15)" : "transparent",
                    color: isActive ? "#00D4FF" : "#94a3b8",
                    border: `1px solid ${isActive ? "#00D4FF" : "#1E2A3A"}`,
                  }}
                >
                  {v} <span style={{ color: "#64748b", fontSize: 11, marginLeft: 4 }}>({count})</span>
                  {runs.length > 0 && v !== "ALL" && (
                    <span style={{ color: "#64748b", fontSize: 10, marginLeft: 6 }}>
                      {((count / runs.length) * 100).toFixed(0)}%
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {filtered.length === 0 && (
            <div className="rounded-xl border p-8 text-center" style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
              <div className="text-4xl mb-2">🏭</div>
              <p className="text-gray-300 mb-1">
                {runs.length === 0 ? "Aún no hay corridas ejecutadas" : `Sin runs con verdict ${filter}`}
              </p>
              <p className="text-xs text-gray-500">
                Cada run cuesta ~$0.06 en LLM y produce un veredicto pass/kill/iterate.
              </p>
            </div>
          )}

          {filtered.length > 0 && (
            <div className="rounded-xl border overflow-hidden" style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottomColor: "#1E2A3A", borderBottomWidth: "1px" }}>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Idea</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Veredicto</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Confianza</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Slug</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Costo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((r) => (
                    <tr
                      key={r.run_id}
                      className="hover:bg-white/[0.02] cursor-pointer"
                      onClick={() => router.push(`/cazar?run_id=${r.run_id}`)}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-medium text-gray-100">{r.idea_title}</p>
                          <p className="text-xs text-gray-500 font-mono">{r.run_id.slice(0, 8)}…</p>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <VerdictBadge verdict={(r.verdict.toUpperCase() as "PASS" | "KILL" | "ITERATE") || "ITERATE"} size="sm" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "#1E2A3A" }}>
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.round(r.confidence * 100)}%`,
                                backgroundColor: r.confidence >= 0.8 ? "#00E5A0" : r.confidence >= 0.6 ? "#FFB800" : "#FF4444",
                              }}
                            />
                          </div>
                          <span className="text-gray-300 font-mono text-xs">{r.confidence.toFixed(2)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs px-2 py-1 rounded" style={{ backgroundColor: "#1E2A3A", color: "#00D4FF" }}>
                          {r.landing_slug || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-300">${r.cost_usd_estimated.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
