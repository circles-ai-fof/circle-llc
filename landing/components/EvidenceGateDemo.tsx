"use client";

import { useState } from "react";

type Verdict = "PASS" | "KILL" | "ITERATE";

interface SimResult {
  idea: string;
  verdict: Verdict;
  confidence: number;
  nextStep: string;
  icp: string;
  signal: string;
}

const MOCK_RESULTS: Record<Verdict, Omit<SimResult, "idea">> = {
  PASS: {
    verdict: "PASS",
    confidence: 87,
    nextStep: "Avanzar a Sprint M1 — arquitectura y build",
    icp: "Founders LATAM, 25-40 años, pre-seed, 1-3 intentos previos",
    signal: "CTR anuncio: 4.2% · Leads capturados: 34 · CPA: $8.50",
  },
  ITERATE: {
    verdict: "ITERATE",
    confidence: 61,
    nextStep: "Refinar ICP — ajustar messaging para segmento B2B",
    icp: "PyMEs manufactureras, LatAm, 10-50 empleados, sin equipo tech",
    signal: "CTR anuncio: 2.1% · Leads capturados: 11 · CPA: $22.00",
  },
  KILL: {
    verdict: "KILL",
    confidence: 23,
    nextStep: "Pivotar idea — mercado insuficiente en este segmento",
    icp: "Estudiantes universitarios, 18-24 años, segmento recreativo",
    signal: "CTR anuncio: 0.4% · Leads capturados: 2 · CPA: $87.00",
  },
};

function getVerdictForIdea(idea: string): Verdict {
  const lower = idea.toLowerCase();
  if (
    lower.includes("b2b") ||
    lower.includes("empresa") ||
    lower.includes("saas") ||
    lower.includes("software") ||
    lower.includes("plataforma") ||
    lower.includes("automatizar") ||
    lower.length > 80
  ) {
    return "PASS";
  }
  if (
    lower.includes("app") ||
    lower.includes("servicio") ||
    lower.includes("marketplace") ||
    lower.length > 40
  ) {
    return "ITERATE";
  }
  return "KILL";
}

const verdictConfig: Record<Verdict, { color: string; bg: string; border: string; label: string }> = {
  PASS: {
    color: "text-green-400",
    bg: "bg-green-400/10",
    border: "border-green-400/30",
    label: "PASS — El mercado responde",
  },
  KILL: {
    color: "text-red-400",
    bg: "bg-red-400/10",
    border: "border-red-400/30",
    label: "KILL — Sin señal de mercado",
  },
  ITERATE: {
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    border: "border-amber-400/30",
    label: "ITERATE — Señal débil, refinar",
  },
};

export default function EvidenceGateDemo() {
  const [idea, setIdea] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);

  const handleSimulate = () => {
    if (!idea.trim() || loading) return;
    setLoading(true);
    setResult(null);

    setTimeout(() => {
      const verdict = getVerdictForIdea(idea);
      setResult({ idea, ...MOCK_RESULTS[verdict] });
      setLoading(false);
    }, 2000);
  };

  const handleReset = () => {
    setResult(null);
    setIdea("");
  };

  return (
    <section id="evidence-gate" className="py-24 px-6 bg-bg-card/50">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-10">
          <span className="inline-block px-3 py-1 rounded-full bg-accent/10 text-accent text-xs font-medium border border-accent/20 mb-4">
            Demo interactivo
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
            Simula tu Evidence Gate
          </h2>
          <p className="text-text-primary/60 text-lg">
            Describe tu idea y ve cómo funciona el proceso de validación.
          </p>
        </div>

        {/* Input card */}
        {!result && (
          <div className="bg-bg-card border border-white/5 rounded-2xl p-8">
            <label className="block text-sm font-medium text-text-primary/70 mb-3">
              ¿Qué problema quieres resolver y para quién?
            </label>
            <textarea
              className="w-full bg-bg border border-white/10 rounded-xl px-4 py-3 text-text-primary placeholder-text-primary/30 resize-none focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20 transition-all text-sm leading-relaxed"
              rows={4}
              placeholder="Ej: Una plataforma SaaS que ayuda a PyMEs en LATAM a automatizar su contabilidad con IA, eliminando el tiempo que los dueños pierden en Excel..."
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              maxLength={500}
            />
            <div className="flex items-center justify-between mt-2 mb-6">
              <span className="text-xs text-text-primary/30">
                {idea.length}/500 caracteres
              </span>
              <span className="text-xs text-text-primary/30">
                Sin formato necesario · Solo describe tu idea
              </span>
            </div>

            <button
              onClick={handleSimulate}
              disabled={!idea.trim() || loading}
              className="w-full py-3.5 rounded-xl font-semibold text-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed bg-accent text-bg hover:bg-accent/90 active:scale-95"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-bg/30 border-t-bg rounded-full animate-spin" />
                  Simulando evidence-gate...
                </span>
              ) : (
                "Simular evidence-gate →"
              )}
            </button>

            <p className="text-center text-xs text-text-primary/30 mt-4">
              Demo estático · No llama API real · Solo para ilustrar el proceso
            </p>
          </div>
        )}

        {/* Result card */}
        {result && (
          <div className="bg-bg-card border border-white/5 rounded-2xl p-8 space-y-6">
            {/* Idea recap */}
            <div>
              <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium">
                Idea evaluada
              </span>
              <p className="mt-1 text-sm text-text-primary/80 leading-relaxed bg-bg rounded-lg px-4 py-3 border border-white/5">
                &ldquo;{result.idea}&rdquo;
              </p>
            </div>

            {/* Verdict */}
            <div
              className={`rounded-xl p-5 ${verdictConfig[result.verdict].bg} border ${verdictConfig[result.verdict].border}`}
            >
              <div className="flex items-center justify-between mb-3">
                <span
                  className={`text-2xl font-black ${verdictConfig[result.verdict].color} tracking-wider`}
                >
                  {result.verdict}
                </span>
                <div className="text-right">
                  <span className="text-xs text-text-primary/40 block">
                    Confianza
                  </span>
                  <span
                    className={`text-2xl font-bold ${verdictConfig[result.verdict].color}`}
                  >
                    {result.confidence}%
                  </span>
                </div>
              </div>
              <p className={`text-sm font-medium ${verdictConfig[result.verdict].color}`}>
                {verdictConfig[result.verdict].label}
              </p>
            </div>

            {/* Details grid */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-bg rounded-xl p-4 border border-white/5">
                <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium block mb-2">
                  ICP detectado
                </span>
                <p className="text-sm text-text-primary/80 leading-relaxed">
                  {result.icp}
                </p>
              </div>
              <div className="bg-bg rounded-xl p-4 border border-white/5">
                <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium block mb-2">
                  Señal de mercado (14 días)
                </span>
                <p className="text-sm text-text-primary/80 leading-relaxed font-mono">
                  {result.signal}
                </p>
              </div>
            </div>

            {/* Next step */}
            <div className="flex items-start gap-3 bg-accent/5 rounded-xl p-4 border border-accent/15">
              <svg
                className="w-5 h-5 text-accent shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
              <div>
                <span className="text-xs text-accent font-medium uppercase tracking-wider block mb-1">
                  Siguiente paso
                </span>
                <p className="text-sm text-text-primary/80">{result.nextStep}</p>
              </div>
            </div>

            {/* Reset */}
            <button
              onClick={handleReset}
              className="w-full py-3 rounded-xl text-sm text-text-primary/50 border border-white/10 hover:border-white/20 hover:text-text-primary/70 transition-all duration-200"
            >
              Probar con otra idea
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
