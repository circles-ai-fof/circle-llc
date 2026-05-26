"use client";

import { useState } from "react";
import VerdictBadge from "./VerdictBadge";
import type { Verdict } from "@/lib/mockData";

interface RunResult {
  run_id: string;
  idea_title: string;
  verdict: Verdict;
  confidence: number;
  landing_headline: string;
  landing_slug: string;
  rationale: string;
  cost_usd_estimated: number;
  steps_used: number;
}

interface RunFormProps {
  onClose: () => void;
}

// Demo mode: simulated result based on topic keywords
function simulateResult(topic: string): RunResult {
  const lower = topic.toLowerCase();
  let verdict: Verdict = "ITERATE";
  let confidence = 0.71;

  if (lower.includes("farma") || lower.includes("salud") || lower.includes("health")) {
    verdict = "PASS";
    confidence = 0.87;
  } else if (lower.includes("crypto") || lower.includes("nft") || lower.includes("metaverso")) {
    verdict = "KILL";
    confidence = 0.91;
  } else if (lower.includes("app") || lower.includes("saas") || lower.includes("pyme")) {
    verdict = "PASS";
    confidence = 0.82;
  }

  const slug = topic
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 40);

  return {
    run_id: `run-demo-${Date.now().toString(36)}`,
    idea_title: topic,
    verdict,
    confidence,
    landing_headline: `${topic} — la solución que el mercado ecuatoriano estaba esperando`,
    landing_slug: slug,
    rationale:
      verdict === "PASS"
        ? `Mercado con demanda real validada. El segmento objetivo muestra alta propensión de compra y baja satisfacción con soluciones actuales. Modelo de monetización viable con CAC estimado < 30 USD.`
        : verdict === "KILL"
        ? `Mercado saturado o señales negativas de demanda. Riesgo regulatorio alto y baja propensión de pago en el segmento LATAM. No se recomienda continuar.`
        : `Concepto prometedor, pero requiere pivote en el segmento objetivo. Se recomienda validar con un piloto reducido antes de comprometer recursos. Confianza suficiente para continuar con ajustes.`,
    cost_usd_estimated: 0.04 + Math.random() * 0.02,
    steps_used: 5,
  };
}

export default function RunForm({ onClose }: RunFormProps) {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isValid = topic.trim().length >= 5;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid) return;

    setLoading(true);
    setError(null);
    setResult(null);

    // Simulate async API call (demo mode)
    await new Promise((resolve) => setTimeout(resolve, 2200));

    try {
      // In production, replace with:
      // const res = await fetch('/api/v1/gate/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic }) });
      // const data = await res.json();
      const data = simulateResult(topic.trim());
      setResult(data);
    } catch {
      setError("Error al conectar con el backend. Verifica que el servidor esté activo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={!loading ? onClose : undefined}
      />

      {/* Modal */}
      <div
        className="relative w-full max-w-lg rounded-2xl border shadow-2xl overflow-hidden"
        style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: "#1E2A3A" }}>
          <div>
            <h2 className="text-lg font-semibold text-white">Nueva Fábrica</h2>
            <p className="text-xs text-gray-500 mt-0.5">Ejecutar EvidenceGateWorkflow</p>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5">
          {!result ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Idea o tema de negocio
                </label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="ej: App de delivery de medicamentos para adultos mayores"
                  disabled={loading}
                  className="w-full px-3.5 py-2.5 rounded-lg text-sm text-gray-100 placeholder-gray-600 border outline-none transition-all focus:ring-1 disabled:opacity-60"
                  style={{
                    backgroundColor: "#0B0F1A",
                    borderColor: "#1E2A3A",
                    "--tw-ring-color": "#00D4FF",
                  } as React.CSSProperties}
                />
                {topic.length > 0 && topic.trim().length < 5 && (
                  <p className="text-xs mt-1" style={{ color: "#FF4444" }}>
                    Mínimo 5 caracteres
                  </p>
                )}
              </div>

              {/* Pipeline steps preview */}
              <div className="rounded-lg p-3 space-y-2" style={{ backgroundColor: "#0B0F1A" }}>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline</p>
                {["idea_hunter", "idea_maturer", "market_validator", "landing_generator", "gate_decider"].map(
                  (agent, i) => (
                    <div key={agent} className="flex items-center gap-2">
                      <span
                        className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                        style={{ backgroundColor: "#1E2A3A", color: "#00D4FF" }}
                      >
                        {i + 1}
                      </span>
                      <span className="text-xs font-mono text-gray-400">{agent}</span>
                    </div>
                  )
                )}
              </div>

              {error && (
                <p className="text-sm rounded-lg px-3 py-2" style={{ color: "#FF4444", backgroundColor: "rgba(255,68,68,0.1)" }}>
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={!isValid || loading}
                className="w-full py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                style={{
                  backgroundColor: isValid && !loading ? "#00D4FF" : "#1E2A3A",
                  color: isValid && !loading ? "#0B0F1A" : "#6B7280",
                }}
              >
                {loading ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Ejecutando 5 agentes...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Ejecutar EvidenceGate
                  </>
                )}
              </button>

              <p className="text-xs text-center text-gray-600">
                Demo mode — resultados simulados sin llamadas API reales
              </p>
            </form>
          ) : (
            <div className="space-y-4">
              {/* Result header */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-500 mb-0.5">Idea analizada</p>
                  <p className="font-semibold text-gray-100 text-base">{result.idea_title}</p>
                </div>
                <VerdictBadge verdict={result.verdict} size="lg" />
              </div>

              {/* Confidence */}
              <div className="rounded-lg p-3 flex items-center gap-3" style={{ backgroundColor: "#0B0F1A" }}>
                <div className="flex-1">
                  <div className="flex justify-between mb-1">
                    <span className="text-xs text-gray-500">Confianza</span>
                    <span className="text-xs font-mono font-bold" style={{ color: "#00D4FF" }}>
                      {(result.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "#1E2A3A" }}>
                    <div
                      className="h-full rounded-full transition-all duration-1000"
                      style={{
                        width: `${result.confidence * 100}%`,
                        backgroundColor:
                          result.confidence >= 0.8
                            ? "#00E5A0"
                            : result.confidence >= 0.6
                            ? "#FFB800"
                            : "#FF4444",
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Headline */}
              <div className="rounded-lg p-3" style={{ backgroundColor: "#0B0F1A" }}>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
                  Landing Headline
                </p>
                <p className="text-sm text-gray-200 italic">&ldquo;{result.landing_headline}&rdquo;</p>
                <p className="text-xs font-mono mt-1.5" style={{ color: "#00D4FF" }}>
                  /{result.landing_slug}
                </p>
              </div>

              {/* Rationale */}
              <div className="rounded-lg p-3" style={{ backgroundColor: "#0B0F1A" }}>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
                  Racional
                </p>
                <p className="text-sm text-gray-300 leading-relaxed">{result.rationale}</p>
              </div>

              {/* Meta */}
              <div className="flex gap-3 text-xs text-gray-500">
                <span>
                  <span className="font-mono" style={{ color: "#00D4FF" }}>{result.steps_used}</span> agentes
                </span>
                <span>·</span>
                <span>
                  <span className="font-mono" style={{ color: "#00D4FF" }}>
                    ${result.cost_usd_estimated.toFixed(4)}
                  </span> USD
                </span>
                <span>·</span>
                <span className="font-mono text-gray-600">{result.run_id}</span>
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => { setResult(null); setTopic(""); }}
                  className="flex-1 py-2 rounded-lg text-sm font-medium border transition-colors hover:bg-white/5"
                  style={{ borderColor: "#1E2A3A", color: "#9CA3AF" }}
                >
                  Nuevo análisis
                </button>
                <button
                  onClick={onClose}
                  className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors"
                  style={{ backgroundColor: "#00D4FF", color: "#0B0F1A" }}
                >
                  Cerrar
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
