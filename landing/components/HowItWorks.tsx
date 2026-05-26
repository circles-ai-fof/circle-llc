const steps = [
  {
    number: "01",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    ),
    title: "Describes tu idea",
    description:
      "En 30 segundos cuéntanos qué problema resuelves y para quién. Sin decks, sin formatos.",
    time: "30 segundos",
  },
  {
    number: "02",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
    title: "5 agentes IA diseñan el test",
    description:
      "Nuestros agentes definen ICP, propuesta de valor, copy del anuncio y métricas de éxito específicas para tu vertical.",
    time: "Automático",
  },
  {
    number: "03",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: "Landing + anuncios reales",
    description:
      "Lanzamos una landing page y campaña de anuncios reales en tu vertical. Tráfico real, no encuestas.",
    time: "Día 1–3",
  },
  {
    number: "04",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: "Decisión con datos en 14 días",
    description:
      "El Evidence Gate evalúa las métricas y emite veredicto: PASS para construir, KILL para pivotar, o ITERATE para refinar.",
    time: "Día 14",
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <span className="inline-block px-3 py-1 rounded-full bg-accent/10 text-accent text-xs font-medium border border-accent/20 mb-4">
            EvidenceGate Workflow
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
            Cómo funciona la fábrica
          </h2>
          <p className="text-text-primary/60 max-w-xl mx-auto text-lg">
            Un proceso lineal de 14 días que convierte tu idea en evidencia de
            mercado real.
          </p>
        </div>

        {/* Steps */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, index) => (
            <div
              key={step.number}
              className="relative group"
            >
              {/* Connector line (not on last item) */}
              {index < steps.length - 1 && (
                <div className="hidden lg:block absolute top-8 left-full w-full h-px bg-gradient-to-r from-accent/30 to-transparent z-10 -translate-y-0.5" />
              )}

              <div className="bg-bg-card border border-white/5 rounded-xl p-6 h-full hover:border-accent/20 transition-all duration-300 group-hover:bg-white/[0.02]">
                {/* Step number */}
                <div className="flex items-center justify-between mb-4">
                  <span className="text-4xl font-black text-accent/20 leading-none">
                    {step.number}
                  </span>
                  <span className="text-xs text-text-primary/40 bg-white/5 px-2 py-0.5 rounded-full">
                    {step.time}
                  </span>
                </div>

                {/* Icon */}
                <div className="w-11 h-11 rounded-lg bg-accent/10 text-accent flex items-center justify-center mb-4 group-hover:bg-accent/15 transition-colors">
                  {step.icon}
                </div>

                {/* Content */}
                <h3 className="text-base font-semibold text-text-primary mb-2">
                  {step.title}
                </h3>
                <p className="text-sm text-text-primary/55 leading-relaxed">
                  {step.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Analogy quote */}
        <div className="mt-12 p-6 rounded-xl bg-bg-card border border-accent/10 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-accent to-transparent" />
          <blockquote className="pl-4">
            <p className="text-text-primary/70 italic text-base leading-relaxed">
              &ldquo;No importa si hacemos brownies o tortas — lo que importa es
              tener el horno, los ingredientes y el sistema.&rdquo;
            </p>
            <cite className="block mt-2 text-sm text-accent font-medium not-italic">
              — JF Núñez, Founder · circles-ai.ai
            </cite>
          </blockquote>
        </div>
      </div>
    </section>
  );
}
