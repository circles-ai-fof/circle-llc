"use client";

import { useState } from "react";
import RunsTable from "@/components/RunsTable";
import RunForm from "@/components/RunForm";
import VerdictBadge from "@/components/VerdictBadge";
import { mockRuns } from "@/lib/mockData";
import type { Verdict } from "@/lib/mockData";

type FilterVerdict = Verdict | "ALL";

export default function FabricasPage() {
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<FilterVerdict>("ALL");

  const filtered = filter === "ALL" ? mockRuns : mockRuns.filter((r) => r.verdict === filter);

  const filters: { label: string; value: FilterVerdict }[] = [
    { label: "Todos", value: "ALL" },
    { label: "PASS", value: "PASS" },
    { label: "ITERATE", value: "ITERATE" },
    { label: "KILL", value: "KILL" },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Fábricas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Historial completo de ideas analizadas por EvidenceGateWorkflow
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

      {/* Verdict summary cards */}
      <div className="grid grid-cols-3 gap-4">
        {(["PASS", "ITERATE", "KILL"] as Verdict[]).map((v) => {
          const count = mockRuns.filter((r) => r.verdict === v).length;
          return (
            <button
              key={v}
              onClick={() => setFilter(filter === v ? "ALL" : v)}
              className="rounded-xl border p-4 text-left transition-all hover:border-opacity-60"
              style={{
                backgroundColor: filter === v ? "rgba(0,212,255,0.05)" : "#111827",
                borderColor: filter === v ? "rgba(0,212,255,0.3)" : "#1E2A3A",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <VerdictBadge verdict={v} size="sm" />
                <span className="text-2xl font-bold text-white">{count}</span>
              </div>
              <p className="text-xs text-gray-500">
                {((count / mockRuns.length) * 100).toFixed(0)}% del total
              </p>
            </button>
          );
        })}
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-2">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className="px-3 py-1.5 rounded-full text-xs font-medium transition-all"
            style={{
              backgroundColor: filter === f.value ? "#00D4FF" : "#1E2A3A",
              color: filter === f.value ? "#0B0F1A" : "#9CA3AF",
            }}
          >
            {f.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-500">
          {filtered.length} resultado{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      {filtered.length > 0 ? (
        <RunsTable runs={filtered} />
      ) : (
        <div
          className="rounded-xl border p-12 text-center"
          style={{ borderColor: "#1E2A3A", backgroundColor: "#111827" }}
        >
          <p className="text-gray-500 text-sm">No hay runs con el filtro seleccionado.</p>
        </div>
      )}

      {showForm && <RunForm onClose={() => setShowForm(false)} />}
    </div>
  );
}
