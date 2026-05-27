// Pre-generated pool of REAL EvidenceGateWorkflow runs.
// Why pre-generated? See ADR-009: exposing the live $0.06-per-call endpoint
// to public landing traffic would let bots drain the LLM budget. This pool
// covers the most common queries via keyword matching at zero runtime cost.
//
// Regenerate with:  python scripts/generate_demo_pool.py

import runsJson from "./demo-runs.json";

export type DemoRun = {
  id: string;
  category: string;
  keywords: string[];
  topic_input: string;
  idea: {
    title: string;
    description: string;
    target_market: string;
    problem_statement: string;
    proposed_solution: string;
    vertical_category: string;
  };
  value_proposition: string;
  test_design: {
    hypothesis: string;
    ad_budget_usd: number;
    test_duration_days: number;
    target_ctr: number;
    target_conversion_rate: number;
  };
  landing: {
    headline: string;
    subheadline: string;
    value_props: string[];
    cta_text: string;
    social_proof: string;
    domain_slug: string;
  };
  decision: {
    verdict: "pass" | "kill" | "iterate";
    confidence: number;
    rationale: string;
    next_steps: string[];
    ensemble_votes: string[];
    needs_human_review: boolean;
  };
  metadata: {
    steps_used: number | null;
    cost_usd_estimated: number | null;
    generated_at: number;
  };
};

export const demoPool: DemoRun[] = runsJson as unknown as DemoRun[];

// Eager validation — runs at module import (i.e. once at build / first render).
// If the JSON is malformed or empty, the landing build fails fast.
(function _validate() {
  if (!Array.isArray(demoPool) || demoPool.length === 0) {
    throw new Error(
      "demo-pool: empty or invalid — regenerate with `python scripts/generate_demo_pool.py`"
    );
  }
  for (const [i, e] of demoPool.entries()) {
    if (!e.id || !e.keywords?.length || !e.decision?.verdict) {
      throw new Error(`demo-pool[${i}]: missing id/keywords/decision`);
    }
    if (!["pass", "kill", "iterate"].includes(e.decision.verdict)) {
      throw new Error(`demo-pool[${i}] (${e.id}): bad verdict ${e.decision.verdict}`);
    }
  }
})();

/**
 * Find the demo run that best matches the user's input topic.
 * Strategy: tokenize input, count matched keywords per pool entry,
 * break ties by category preference inferred from input.
 *
 * Returns the closest match plus a similarity hint (0..1) so the UI can
 * decide whether to show "exact match" vs "closest available".
 */
export function matchDemoRun(input: string): {
  run: DemoRun;
  score: number;
  exact: boolean;
} {
  if (demoPool.length === 0) {
    throw new Error("demo pool is empty — run scripts/generate_demo_pool.py");
  }

  const tokens = tokenize(input);
  const tokenSet = new Set(tokens);

  let bestRun = demoPool[0];
  let bestScore = 0;

  for (const run of demoPool) {
    const hits = run.keywords.filter((k) => tokenSet.has(k.toLowerCase())).length;
    if (hits === 0) continue;
    // Combined score: raw hits (signals more relevance for longer keyword lists)
    // + jaccard-style ratio normalized by union size (rewards both sides).
    const union = new Set([...tokenSet, ...run.keywords.map((k) => k.toLowerCase())]).size;
    const jaccard = hits / union;
    // Composite: 60% raw hit weight, 40% jaccard normalization
    const score = 0.6 * Math.min(1, hits / 3) + 0.4 * jaccard;
    if (score > bestScore) {
      bestScore = score;
      bestRun = run;
    }
  }

  // Treat scores >= 0.35 as effectively exact match
  const exact = bestScore >= 0.35;
  return { run: bestRun, score: bestScore, exact };
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // strip accents
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 3);
}
