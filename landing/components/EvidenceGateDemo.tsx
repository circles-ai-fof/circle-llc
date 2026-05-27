"use client";

import { useState } from "react";
import { matchDemoRun, type DemoRun } from "@/lib/demo-pool";

type Verdict = "PASS" | "KILL" | "ITERATE";

type DemoResult = {
  input: string;
  run: DemoRun;
  matchScore: number;
  exactMatch: boolean;
};

const verdictConfig: Record<
  Verdict,
  { color: string; bg: string; border: string; label: string }
> = {
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

function verdictUpper(v: string): Verdict {
  const u = v.toUpperCase();
  if (u === "PASS" || u === "KILL" || u === "ITERATE") return u;
  return "ITERATE";
}

export default function EvidenceGateDemo() {
  const [idea, setIdea] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DemoResult | null>(null);

  const handleSimulate = () => {
    if (!idea.trim() || loading) return;
    setLoading(true);
    setResult(null);

    // Tiny artificial delay so the user sees the pipeline animating
    setTimeout(() => {
      const match = matchDemoRun(idea);
      setResult({
        input: idea,
        run: match.run,
        matchScore: match.score,
        exactMatch: match.exact,
      });
      setLoading(false);
    }, 1200);
  };

  const handleReset = () => {
    setResult(null);
    setIdea("");
  };

  const verdict = result ? verdictUpper(result.run.decision.verdict) : "ITERATE";

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
                  Buscando corrida real más cercana...
                </span>
              ) : (
                "Simular evidence-gate →"
              )}
            </button>

            <p className="text-center text-xs text-text-primary/30 mt-4">
              Resultados reales del workflow Claude + GPT + Gemini · Cacheados
              para no exponer el endpoint pagado al público
            </p>
          </div>
        )}

        {/* Result card */}
        {result && (
          <div className="bg-bg-card border border-white/5 rounded-2xl p-8 space-y-6">
            {/* Match quality banner */}
            <div
              className={`text-xs px-3 py-2 rounded-lg border ${
                result.exactMatch
                  ? "bg-accent/10 border-accent/30 text-accent"
                  : "bg-amber-400/10 border-amber-400/30 text-amber-400"
              }`}
            >
              {result.exactMatch
                ? `✓ Match cercano (${Math.round(result.matchScore * 100)}%) — mostrando una corrida real del pool`
                : `≈ Match aproximado (${Math.round(result.matchScore * 100)}%) — la corrida más cercana del pool. Para ver tu idea EXACTA, solicita acceso.`}
            </div>

            {/* Idea recap */}
            <div>
              <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium">
                Tu pregunta
              </span>
              <p className="mt-1 text-sm text-text-primary/80 leading-relaxed bg-bg rounded-lg px-4 py-3 border border-white/5">
                &ldquo;{result.input}&rdquo;
              </p>
            </div>

            {/* Idea (real workflow output) */}
            <div>
              <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium">
                Idea refinada por el workflow
              </span>
              <p className="mt-1 text-sm text-text-primary font-semibold">
                {result.run.idea.title}
              </p>
              <p className="mt-1 text-xs text-text-primary/60 leading-relaxed">
                {result.run.idea.description}
              </p>
            </div>

            {/* Verdict */}
            <div
              className={`rounded-xl p-5 ${verdictConfig[verdict].bg} border ${verdictConfig[verdict].border}`}
            >
              <div className="flex items-center justify-between mb-3">
                <span
                  className={`text-2xl font-black ${verdictConfig[verdict].color} tracking-wider`}
                >
                  {verdict}
                </span>
                <div className="text-right">
                  <span className="text-xs text-text-primary/40 block">
                    Confianza
                  </span>
                  <span
                    className={`text-2xl font-bold ${verdictConfig[verdict].color}`}
                  >
                    {Math.round(result.run.decision.confidence * 100)}%
                  </span>
                </div>
              </div>
              <p className={`text-sm font-medium ${verdictConfig[verdict].color}`}>
                {verdictConfig[verdict].label}
              </p>
              <p className="text-xs text-text-primary/60 mt-3 leading-relaxed">
                {result.run.decision.rationale.slice(0, 280)}
                {result.run.decision.rationale.length > 280 ? "..." : ""}
              </p>
            </div>

            {/* Details grid */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-bg rounded-xl p-4 border border-white/5">
                <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium block mb-2">
                  ICP detectado
                </span>
                <p className="text-sm text-text-primary/80 leading-relaxed">
                  {result.run.idea.target_market}
                </p>
              </div>
              <div className="bg-bg rounded-xl p-4 border border-white/5">
                <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium block mb-2">
                  Test propuesto (14 días)
                </span>
                <p className="text-sm text-text-primary/80 leading-relaxed font-mono">
                  Budget: ${result.run.test_design.ad_budget_usd}
                  <br />
                  Target CTR: {(result.run.test_design.target_ctr * 100).toFixed(1)}%
                  <br />
                  Target CVR: {(result.run.test_design.target_conversion_rate * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Ensemble votes (if multi-LLM was used) */}
            {result.run.decision.ensemble_votes && result.run.decision.ensemble_votes.length > 0 && (
              <div className="bg-bg rounded-xl p-4 border border-white/5">
                <span className="text-xs text-text-primary/40 uppercase tracking-wider font-medium block mb-2">
                  Votos del ensemble (Claude + GPT + Gemini)
                </span>
                <div className="space-y-1 font-mono text-xs text-text-primary/70">
                  {result.run.decision.ensemble_votes.map((v, i) => (
                    <div key={i}>• {v}</div>
                  ))}
                </div>
              </div>
            )}

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
                  Siguiente paso recomendado
                </span>
                <p className="text-sm text-text-primary/80">
                  {result.run.decision.next_steps[0] ?? "Iterar el copy y re-medir."}
                </p>
              </div>
            </div>

            {/* Reset */}
            <button
              onClick={handleReset}
              className="w-full py-3 rounded-xl text-sm text-text-primary/50 border border-white/10 hover:border-white/20 hover:text-text-primary/70 transition-all duration-200"
            >
              Probar con otra idea
            </button>

            {/* Provenance footer */}
            <p className="text-center text-xs text-text-primary/30">
              Corrida generada el{" "}
              {new Date(result.run.metadata.generated_at * 1000).toLocaleDateString("es", {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}{" "}
              · costo real: ${result.run.metadata.cost_usd_estimated?.toFixed(2)} USD
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
