import HowItWorks from "@/components/HowItWorks";
import ForFounders from "@/components/ForFounders";
import EvidenceGateDemo from "@/components/EvidenceGateDemo";

export default function HomePage() {
  return (
    <>
      {/* ─── Hero ─── */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-16">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-bg via-bg to-bg-card" />

        {/* Radial glow */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full bg-accent/5 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-green/5 blur-3xl pointer-events-none" />

        {/* Grid pattern overlay */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.3) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />

        <div className="relative z-10 max-w-5xl mx-auto px-6 text-center">
          {/* Badge */}
          <div className="flex justify-center mb-8">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent/10 text-accent text-xs font-medium border border-accent/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent" />
              </span>
              Powered by Claude AI · Reganti-aligned architecture
            </span>
          </div>

          {/* Headline */}
          <h1 className="text-5xl md:text-6xl lg:text-7xl font-black text-text-primary leading-tight mb-6 tracking-tight">
            De idea a evidencia
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent via-accent to-green">
              en 14 días
            </span>
          </h1>

          {/* Subheadline */}
          <p className="text-lg md:text-xl text-text-primary/60 max-w-2xl mx-auto mb-10 leading-relaxed">
            Factory of Factories valida si tu idea tiene mercado real antes de
            construir una sola línea de código.
            <span className="block mt-2 text-text-primary/40 text-base">
              5 agentes IA · Landing real · Anuncios reales · Decisión con datos.
            </span>
          </p>

          {/* CTA buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
            <a
              href="#how-it-works"
              className="px-8 py-4 rounded-xl bg-accent text-bg font-bold text-base hover:bg-accent/90 active:scale-95 transition-all duration-200 shadow-lg shadow-accent/20"
            >
              Validar mi idea →
            </a>
            <a
              href="#evidence-gate"
              className="px-8 py-4 rounded-xl bg-white/5 text-text-primary/80 font-medium text-base border border-white/10 hover:bg-white/10 hover:border-white/20 transition-all duration-200"
            >
              Ver demo interactivo
            </a>
          </div>

          {/* Stats bar */}
          <div className="flex flex-wrap justify-center gap-8 md:gap-12">
            {[
              { value: "14 días", label: "de evidencia real" },
              { value: "5 agentes", label: "IA especializados" },
              { value: "3 veredictos", label: "PASS · KILL · ITERATE" },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-2xl font-black text-accent">{stat.value}</div>
                <div className="text-xs text-text-primary/40 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 text-text-primary/20">
          <span className="text-xs">scroll</span>
          <svg className="w-4 h-4 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </section>

      {/* ─── How It Works ─── */}
      <HowItWorks />

      {/* ─── For Founders ─── */}
      <ForFounders />

      {/* ─── Evidence Gate Demo ─── */}
      <EvidenceGateDemo />

      {/* ─── Final CTA ─── */}
      <section className="py-24 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
            ¿Tienes una idea?
          </h2>
          <p className="text-text-primary/60 text-lg mb-10">
            No la construyas a ciegas. Valídala primero con evidencia real.
          </p>
          <a
            href="#evidence-gate"
            className="inline-block px-10 py-4 rounded-xl bg-accent text-bg font-bold text-base hover:bg-accent/90 active:scale-95 transition-all duration-200 shadow-lg shadow-accent/20"
          >
            Empezar validación gratuita →
          </a>
          <p className="text-xs text-text-primary/30 mt-4">
            Demo disponible · Sin registro requerido
          </p>
        </div>
      </section>
    </>
  );
}
