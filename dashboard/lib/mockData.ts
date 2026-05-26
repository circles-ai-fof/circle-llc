export type Verdict = "PASS" | "KILL" | "ITERATE";

export interface Run {
  id: string;
  idea_title: string;
  verdict: Verdict;
  confidence: number;
  landing_slug: string;
  cost_usd: number;
  date: string;
  rationale?: string;
  landing_headline?: string;
}

export const mockRuns: Run[] = [
  {
    id: "run-001",
    idea_title: "CapitalAgil PYME Ecuador",
    verdict: "ITERATE",
    confidence: 0.72,
    landing_slug: "capital-agil-pyme",
    cost_usd: 0.05,
    date: "2026-05-26",
    rationale:
      "El mercado objetivo tiene demanda clara, pero el modelo de monetización requiere ajuste. Se recomienda validar con pilotos en Quito y Guayaquil antes de escalar.",
    landing_headline: "Crédito ágil para la PYME ecuatoriana que no tiene tiempo que perder",
  },
  {
    id: "run-002",
    idea_title: "FarmaRapido Adultos Mayores",
    verdict: "PASS",
    confidence: 0.89,
    landing_slug: "farmarapido-ec",
    cost_usd: 0.04,
    date: "2026-05-26",
    rationale:
      "Alta demanda insatisfecha en el segmento +60 años. El mercado ecuatoriano muestra brecha de servicio de última milla en medicamentos. Viabilidad económica confirmada.",
    landing_headline: "Tus medicamentos en 30 minutos, sin salir de casa",
  },
  {
    id: "run-003",
    idea_title: "NominaFacil PYME",
    verdict: "PASS",
    confidence: 0.85,
    landing_slug: "nomina-facil-ec",
    cost_usd: 0.05,
    date: "2026-05-26",
    rationale:
      "Nicho desatendido con regulación compleja (IESS, SRI). Competencia débil en el segmento micro-empresa. TAM estimado $12M/año en Ecuador.",
    landing_headline: "Nómina y IESS en 5 minutos, para PYMES que sí pagan bien",
  },
];

export interface Agent {
  id: string;
  name: string;
  scope: string;
  status: "active" | "deferred";
  description: string;
}

export const mockAgents: Agent[] = [
  {
    id: "idea_hunter",
    name: "idea_hunter",
    scope: "Búsqueda de oportunidades de mercado",
    status: "active",
    description:
      "Explora tendencias, señales de demanda y brechas de mercado en verticales objetivo para generar ideas de negocio con potencial.",
  },
  {
    id: "idea_maturer",
    name: "idea_maturer",
    scope: "Maduración y estructuración de ideas",
    status: "active",
    description:
      "Toma ideas crudas y las estructura en propuestas de valor claras, definiendo cliente objetivo, problema, solución y métricas clave.",
  },
  {
    id: "market_validator",
    name: "market_validator",
    scope: "Validación de mercado y competencia",
    status: "active",
    description:
      "Analiza TAM/SAM/SOM, competidores directos e indirectos, y barreras de entrada para estimar la viabilidad del mercado.",
  },
  {
    id: "landing_generator",
    name: "landing_generator",
    scope: "Generación de landing pages y copy",
    status: "active",
    description:
      "Produce headline, slug, copy persuasivo y estructura de landing page optimizada para captura de leads tempranos.",
  },
  {
    id: "gate_decider",
    name: "gate_decider",
    scope: "Decisión final PASS/KILL/ITERATE",
    status: "active",
    description:
      "Consolida evidencia de todos los agentes y emite veredicto final con nivel de confianza, justificación y próximos pasos.",
  },
];

export function computeStats(runs: Run[]) {
  const total = runs.length;
  const passed = runs.filter((r) => r.verdict === "PASS").length;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;
  const avgConfidence =
    total > 0
      ? (runs.reduce((sum, r) => sum + r.confidence, 0) / total).toFixed(2)
      : "0.00";
  const totalCost = runs.reduce((sum, r) => sum + r.cost_usd, 0).toFixed(3);

  return { total, passRate, avgConfidence, totalCost };
}
