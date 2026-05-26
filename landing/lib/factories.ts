// Catálogo de fábricas activas — un slug por idea que pasó del enricher.
// Estos datos vienen de EvidenceGateWorkflow.run(...) y se copian aquí
// para servir landing estáticos. M3+ leerá esto de la Outcome DB.

export type Factory = {
  slug: string;
  title: string;
  status: "active" | "iterate" | "paused";
  headline: string;
  subheadline: string;
  value_props: string[];
  cta_text: string;
  social_proof: string;
  target_market: string;
  problem_statement: string;
  proposed_solution: string;
  ad_url?: string; // dónde apuntan los anuncios
  test_started_at?: string;
  test_ends_at?: string;
  test_budget_usd?: number;
};

export const factories: Record<string, Factory> = {
  "techpulse-latam": {
    slug: "techpulse-latam",
    title: "TechPulse LATAM",
    status: "active",
    headline: "Publica noticias tech antes que TechCrunch llegue a tu audiencia",
    subheadline:
      "Pipeline de IA que clasifica, traduce y prepara borradores de noticias tech globales — tu equipo revisa y publica en un clic.",
    value_props: [
      "Detección automática 24/7 de RSS, NewsAPI, X/Twitter con filtro LATAM",
      "Borradores en español listos con contexto regional añadido",
      "Workflow Kanban tipo Trello — aprueba, edita o rechaza en un clic",
      "Publicación automática en tu CMS vía webhook",
    ],
    cta_text: "Reservar acceso temprano",
    social_proof:
      "Validado con 3 medios tech en Colombia, México y Ecuador antes de construir.",
    target_market:
      "Editores y directores de medios digitales tech de 5-30 empleados en Colombia, México y Ecuador",
    problem_statement:
      "Equipos editoriales tech LATAM pierden 4+ horas/día monitoreando fuentes dispersas, con cobertura 6-12 horas tras anglosajones y 34% de noticias irrelevantes publicadas.",
    proposed_solution:
      "Pipeline de IA con LLM fine-tuneado en contexto tech LATAM, ingesta de RSS/NewsAPI/X, workflow Kanban de revisión humana, publicación vía webhook.",
    test_started_at: "2026-05-26",
    test_ends_at: "2026-06-09",
    test_budget_usd: 200,
  },
};

export function getFactory(slug: string): Factory | null {
  return factories[slug] ?? null;
}

export function listFactorySlugs(): string[] {
  return Object.keys(factories);
}
