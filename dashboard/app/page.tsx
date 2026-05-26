"use client";

import { useState } from "react";
import StatsBar from "@/components/StatsBar";
import RunsTable from "@/components/RunsTable";
import RunForm from "@/components/RunForm";
import { mockRuns, computeStats } from "@/lib/mockData";

export default function DashboardPage() {
  const [showForm, setShowForm] = useState(false);
  const stats = computeStats(mockRuns);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Factory of Factories — EvidenceGateWorkflow
          </p>
        </div>
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

      {/* Stats */}
      <StatsBar
        total={stats.total}
        passRate={stats.passRate}
        avgConfidence={stats.avgConfidence}
        totalCost={stats.totalCost}
      />

      {/* Pipeline status banner */}
      <div
        className="rounded-xl border px-4 py-3 flex items-center gap-3"
        style={{ backgroundColor: "rgba(0, 212, 255, 0.05)", borderColor: "rgba(0, 212, 255, 0.2)" }}
      >
        <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: "#00E5A0" }} />
        <span className="text-sm text-gray-300">
          Pipeline activo —{" "}
          <span style={{ color: "#00D4FF" }}>5 agentes</span> listos:{" "}
          idea_hunter, idea_maturer, market_validator, landing_generator, gate_decider
        </span>
      </div>

      {/* Recent runs table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-200">Runs recientes</h2>
          <span className="text-xs text-gray-500">{mockRuns.length} resultados</span>
        </div>
        <RunsTable runs={mockRuns} />
      </div>

      {/* Modal */}
      {showForm && <RunForm onClose={() => setShowForm(false)} />}
    </div>
  );
}
