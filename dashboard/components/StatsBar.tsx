interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}

function StatCard({ label, value, sub, accent = "#00D4FF" }: StatCardProps) {
  return (
    <div
      className="flex-1 rounded-xl p-4 border"
      style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
    >
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-bold" style={{ color: accent }}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

interface StatsBarProps {
  total: number;
  passRate: number;
  avgConfidence: string;
  totalCost: string;
}

export default function StatsBar({ total, passRate, avgConfidence, totalCost }: StatsBarProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard label="Total runs" value={total} sub="ideas analizadas" accent="#00D4FF" />
      <StatCard label="Pass rate" value={`${passRate}%`} sub="ideas validadas" accent="#00E5A0" />
      <StatCard
        label="Confianza promedio"
        value={avgConfidence}
        sub="escala 0–1"
        accent="#FFB800"
      />
      <StatCard label="Costo total" value={`$${totalCost}`} sub="USD estimado" accent="#00D4FF" />
    </div>
  );
}
