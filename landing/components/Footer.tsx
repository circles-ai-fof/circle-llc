export default function Footer() {
  return (
    <footer
      id="contact"
      className="border-t border-white/5 bg-bg-card mt-20"
    >
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid md:grid-cols-3 gap-10">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-lg font-bold text-text-primary">
                circles-ai<span className="text-accent">.ai</span>
              </span>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
              </span>
            </div>
            <p className="text-sm text-text-primary/50 leading-relaxed">
              Factory of Factories — validando ideas de negocio con evidencia
              real antes de escribir una línea de código.
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary/80 mb-4 uppercase tracking-wider">
              Plataforma
            </h3>
            <ul className="space-y-2">
              {["Cómo funciona", "Para founders", "Evidence Gate", "Casos de éxito"].map(
                (link) => (
                  <li key={link}>
                    <a
                      href="#"
                      className="text-sm text-text-primary/50 hover:text-accent transition-colors"
                    >
                      {link}
                    </a>
                  </li>
                )
              )}
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary/80 mb-4 uppercase tracking-wider">
              Contacto
            </h3>
            <ul className="space-y-2">
              <li>
                <a
                  href="mailto:hola@circles-ai.ai"
                  className="text-sm text-text-primary/50 hover:text-accent transition-colors"
                >
                  hola@circles-ai.ai
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-text-primary/50 hover:text-accent transition-colors"
                >
                  Twitter / X
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-sm text-text-primary/50 hover:text-accent transition-colors"
                >
                  LinkedIn
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs text-text-primary/30">
            circles-ai.ai · 2026 · Powered by Anthropic Claude
          </p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-primary/30">Built with</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">
              Claude AI
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-text-primary/40 border border-white/10">
              Reganti-aligned
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
