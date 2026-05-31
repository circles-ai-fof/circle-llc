import type { Run } from "@/types/run";
import VerdictBadge from "./VerdictBadge";

interface RunsTableProps {
  runs: Run[];
}

export default function RunsTable({ runs }: RunsTableProps) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: "#1E2A3A", backgroundColor: "#111827" }}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottomColor: "#1E2A3A", borderBottomWidth: "1px" }}>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Idea
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Veredicto
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Confianza
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Slug
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Costo
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Fecha
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {runs.map((run) => (
              <tr
                key={run.id}
                className="transition-colors hover:bg-white/[0.02] cursor-pointer"
              >
                <td className="px-4 py-3">
                  <div>
                    <p className="font-medium text-gray-100">{run.idea_title}</p>
                    <p className="text-xs text-gray-500 font-mono">{run.id}</p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <VerdictBadge verdict={run.verdict} size="sm" />
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
                          width: `${Math.round(run.confidence * 100)}%`,
                          backgroundColor:
                            run.confidence >= 0.8
                              ? "#00E5A0"
                              : run.confidence >= 0.6
                              ? "#FFB800"
                              : "#FF4444",
                        }}
                      />
                    </div>
                    <span className="text-gray-300 font-mono text-xs">
                      {run.confidence.toFixed(2)}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className="font-mono text-xs px-2 py-1 rounded"
                    style={{ backgroundColor: "#1E2A3A", color: "#00D4FF" }}
                  >
                    {run.landing_slug}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-gray-300 font-mono text-xs">${run.cost_usd.toFixed(3)}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-gray-400 text-xs">{run.date}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
