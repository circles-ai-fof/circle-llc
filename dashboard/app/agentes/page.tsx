"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M7.0 — Cleanup pass: esta página ahora consume el endpoint real
 * /api/v1/admin/status en vez del legacy mockAgents.
 *
 * Muestra los 13 agentes con su status + version + sprint origen.
 */

type AgentStatus = {
  name: string;
  version: string;
  status: string;
  experimental: boolean;
  sprint_origin: string;
};

const STATUS_COLORS: Record<string, string> = {
  "active(workflow)": "#00E5A0",
  "active(on-demand)": "#00D4FF",
  "experimental": "#FFB800",
  "deferred": "#94a3b8",
};

const STATUS_LABELS: Record<string, string> = {
  "active(workflow)": "Activo en workflow",
  "active(on-demand)": "Activo on-demand",
  "experimental": "Experimental",
  "deferred": "Diferido",
};

export default function AgentesPage() {
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await authFetch("/api/v1/admin/status");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setAgents(data.agents);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Particionar por status para la visualización
  const workflowAgents = agents.filter((a) => a.status === "active(workflow)");
  const onDemandAgents = agents.filter((a) => a.status === "active(on-demand)");
  const experimentalAgents = agents.filter((a) => a.status === "experimental");

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white">Agentes</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {agents.length} agentes registrados — {workflowAgents.length} workflow + {onDemandAgents.length} on-demand
          {experimentalAgents.length > 0 ? ` + ${experimentalAgents.length} experimentales` : ""}
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
          {/* Workflow pipeline */}
          <div className="rounded-xl border p-4" style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">
              EvidenceGateWorkflow — {workflowAgents.length} agentes lineales
            </p>
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              {workflowAgents.map((a, i) => (
                <div key={a.name} className="flex items-center gap-2 flex-shrink-0">
                  <div className="text-center">
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold mb-1"
                      style={{ backgroundColor: "rgba(0, 229, 160, 0.15)", color: "#00E5A0" }}
                    >
                      {i + 1}
                    </div>
                    <p className="text-xs text-gray-500 font-mono max-w-[100px] truncate">{a.name}</p>
                  </div>
                  {i < workflowAgents.length - 1 && (
                    <svg className="w-5 h-5 text-gray-700 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Tabla completa */}
          <div className="rounded-xl border overflow-hidden" style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottomColor: "#1E2A3A", borderBottomWidth: "1px" }}>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Agente</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Version</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Sprint origen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {agents.map((a) => (
                  <tr key={a.name} className="hover:bg-white/[0.02]">
                    <td className="px-4 py-3 font-mono text-gray-100">{a.name}</td>
                    <td className="px-4 py-3">
                      <span
                        className="text-xs font-semibold px-2 py-1 rounded"
                        style={{
                          color: STATUS_COLORS[a.status] || "#94a3b8",
                          backgroundColor: `${STATUS_COLORS[a.status] || "#94a3b8"}15`,
                          border: `1px solid ${STATUS_COLORS[a.status] || "#94a3b8"}40`,
                        }}
                      >
                        {STATUS_LABELS[a.status] || a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{a.version}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{a.sprint_origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
