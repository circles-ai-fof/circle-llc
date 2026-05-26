const painPoints = [
  {
    before: "6–18 meses de build antes de saber si hay mercado",
    after: "14 días con datos reales antes de escribir código",
  },
  {
    before: "Encuestas que no predicen comportamiento real de compra",
    after: "Anuncios y landings reales con conversiones medibles",
  },
  {
    before: "Pivot tardío cuando ya invertiste tiempo y capital",
    after: "Kill temprano o build confiado con evidencia",
  },
  {
    before: "Intuición vs. datos — siempre gana la intuición (mal)",
    after: "Gate de decisión objetiva: PASS / KILL / ITERATE",
  },
];

const agents = [
  { name: "idea_hunter", role: "Genera ideas desde tendencias de mercado" },
  { name: "idea_maturer", role: "Define ICP y propuesta de valor" },
  { name: "market_validator", role: "Diseña el experimento de mercado" },
  { name: "landing_generator", role: "Genera copy y landing optimizada" },
  { name: "gate_decider", role: "Evalúa métricas → veredicto final" },
];

export default function ForFounders() {
  return (
    <section id="for-founders" className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        {/* Before / After */}
        <div className="mb-20">
          <div className="text-center mb-12">
            <span className="inline-block px-3 py-1 rounded-full bg-accent/10 text-accent text-xs font-medium border border-accent/20 mb-4">
              Para founders
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
              Antes y después
            </h2>
            <p className="text-text-primary/60 text-lg max-w-xl mx-auto">
              El camino tradicional vs. validación guiada por evidencia.
            </p>
          </div>

          <div className="space-y-3">
            {painPoints.map((point, i) => (
              <div
                key={i}
                className="grid md:grid-cols-2 gap-px rounded-xl overflow-hidden"
              >
                <div className="bg-red-400/5 border border-red-400/10 px-6 py-4 flex items-center gap-3">
                  <span className="text-red-400/60 shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </span>
                  <span className="text-sm text-text-primary/60">{point.before}</span>
                </div>
                <div className="bg-green-400/5 border border-green-400/10 px-6 py-4 flex items-center gap-3">
                  <span className="text-green-400/80 shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <span className="text-sm text-text-primary/80 font-medium">{point.after}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 5 Agents */}
        <div>
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
              Los 5 agentes de la fábrica
            </h2>
            <p className="text-text-primary/60 text-lg max-w-xl mx-auto">
              Cada agente tiene un rol específico en el workflow lineal de
              validación.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            {agents.map((agent, i) => (
              <div
                key={agent.name}
                className="flex items-center gap-4 bg-bg-card border border-white/5 rounded-xl px-6 py-4 hover:border-accent/15 transition-all duration-200 group"
              >
                {/* Step indicator */}
                <div className="w-8 h-8 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0 group-hover:bg-accent/15 transition-colors">
                  <span className="text-xs font-bold text-accent">{i + 1}</span>
                </div>

                {/* Agent name */}
                <code className="text-sm font-mono text-accent/90 bg-accent/5 px-3 py-1 rounded-md border border-accent/10 shrink-0">
                  {agent.name}
                </code>

                {/* Arrow */}
                <span className="text-text-primary/20 hidden md:block">→</span>

                {/* Role */}
                <span className="text-sm text-text-primary/70">{agent.role}</span>
              </div>
            ))}
          </div>

          <p className="text-center text-xs text-text-primary/30 mt-6">
            30+ agentes adicionales archivados hasta M12 — principio de
            complejidad mínima (Reganti 2026)
          </p>
        </div>
      </div>
    </section>
  );
}
