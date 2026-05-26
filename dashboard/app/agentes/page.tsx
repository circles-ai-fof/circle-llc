import { mockAgents } from "@/lib/mockData";

export default function AgentesPage() {
  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Agentes</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Pipeline de 5 agentes — EvidenceGateWorkflow
        </p>
      </div>

      {/* Pipeline visualization */}
      <div
        className="rounded-xl border p-4"
        style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
      >
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">Flujo del pipeline</p>
        <div className="flex items-center gap-2 overflow-x-auto pb-2">
          {mockAgents.map((agent, index) => (
            <div key={agent.id} className="flex items-center gap-2 flex-shrink-0">
              <div className="text-center">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold mb-1"
                  style={{ backgroundColor: "rgba(0, 212, 255, 0.15)", color: "#00D4FF" }}
                >
                  {index + 1}
                </div>
                <p className="text-xs text-gray-500 font-mono max-w-[80px] truncate">{agent.id.split("_")[1]}</p>
              </div>
              {index < mockAgents.length - 1 && (
                <svg className="w-5 h-5 text-gray-700 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
          <div className="flex items-center gap-2 ml-2 flex-shrink-0">
            <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <div className="text-center">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: "rgba(0, 229, 160, 0.15)" }}
              >
                <svg className="w-5 h-5" style={{ color: "#00E5A0" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-xs text-gray-500 mt-1">Output</p>
            </div>
          </div>
        </div>
      </div>

      {/* Agent cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {mockAgents.map((agent, index) => (
          <div
            key={agent.id}
            className="rounded-xl border p-5 space-y-3 hover:border-opacity-60 transition-all"
            style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
          >
            {/* Card header */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5 flex-1 min-w-0">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold flex-shrink-0"
                  style={{ backgroundColor: "rgba(0, 212, 255, 0.12)", color: "#00D4FF" }}
                >
                  {index + 1}
                </div>
                <div className="min-w-0">
                  <p className="font-mono text-sm font-semibold text-gray-100 truncate">{agent.name}</p>
                </div>
              </div>
              <span
                className="flex-shrink-0 inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full"
                style={
                  agent.status === "active"
                    ? { backgroundColor: "rgba(0, 229, 160, 0.12)", color: "#00E5A0" }
                    : { backgroundColor: "rgba(107, 114, 128, 0.12)", color: "#6B7280" }
                }
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: agent.status === "active" ? "#00E5A0" : "#6B7280" }}
                />
                {agent.status === "active" ? "Active" : "Deferred"}
              </span>
            </div>

            {/* Scope */}
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Scope</p>
              <p className="text-sm text-gray-300">{agent.scope}</p>
            </div>

            {/* Description */}
            <p className="text-xs text-gray-500 leading-relaxed">{agent.description}</p>
          </div>
        ))}
      </div>

      {/* Info footer */}
      <div
        className="rounded-xl border px-4 py-3 flex items-center gap-3 text-sm text-gray-400"
        style={{ backgroundColor: "rgba(0, 212, 255, 0.04)", borderColor: "rgba(0, 212, 255, 0.15)" }}
      >
        <svg className="w-4 h-4 flex-shrink-0" style={{ color: "#00D4FF" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Los agentes se orquestan secuencialmente. El costo promedio por run completo es de{" "}
        <span style={{ color: "#00D4FF" }}>$0.04–0.06 USD</span> con Claude Sonnet.
      </div>
    </div>
  );
}
