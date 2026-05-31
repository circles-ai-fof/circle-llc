// M7.8 — Tipos canónicos para runs del EvidenceGateWorkflow.
// Antes vivían en lib/mockData.ts (legacy). Movidos a types/ para que la
// fuente de verdad sea explícita y no se mezcle con seed data.

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
