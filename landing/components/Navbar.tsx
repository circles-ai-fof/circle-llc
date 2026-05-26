export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 backdrop-blur-md bg-bg/80">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <a href="/" className="flex items-center gap-2 group">
          <span className="text-xl font-bold text-text-primary tracking-tight">
            circles-ai
            <span className="text-accent">.ai</span>
          </span>
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
          </span>
        </a>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-8">
          <a
            href="#how-it-works"
            className="text-sm text-text-primary/70 hover:text-accent transition-colors duration-200"
          >
            Cómo funciona
          </a>
          <a
            href="#for-founders"
            className="text-sm text-text-primary/70 hover:text-accent transition-colors duration-200"
          >
            Para founders
          </a>
          <a
            href="#contact"
            className="text-sm text-text-primary/70 hover:text-accent transition-colors duration-200"
          >
            Contacto
          </a>
          <a
            href="#evidence-gate"
            className="text-sm px-4 py-2 rounded-lg bg-accent/10 text-accent border border-accent/30 hover:bg-accent/20 transition-all duration-200 font-medium"
          >
            Validar mi idea
          </a>
        </div>

        {/* Mobile menu button */}
        <button className="md:hidden text-text-primary/70 hover:text-accent transition-colors">
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>
      </div>
    </nav>
  );
}
