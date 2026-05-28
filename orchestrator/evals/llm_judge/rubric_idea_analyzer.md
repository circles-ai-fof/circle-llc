# Rubric: IdeaAnalyzer Output Quality

Evaluates outputs from `idea_analyzer.IdeaAnalyzerAgent.analyze()` —
the triage agent that decides if a captured signal is worth promoting
to a full workflow run (~$0.06).

## Usage

Score each of the 5 criteria from 1 to 5.
- `overall = mean(all criteria)`
- **≥ 4.0**: production-quality, trust the recommendation
- **3.0–3.9**: acceptable, but founder should sanity-check before promoting
- **< 3.0**: re-run or flag for review — agent is misfiring on this signal

When scoring, you have access to:
- The input signal (theme, excerpt, suggested_topic, evidence URLs, source)
- The agent's SignalAnalysis output (market_size_estimate, icp_probable,
  competitors, differentiator, risks, recommendation, reasoning)

## Criterion 1: Recommendation Correctness (1–5)

Evaluates whether `recommendation` (promote / wait_for_more_data / discard)
matches the signal's actual quality.

| Score | Description |
|-------|-------------|
| 5 | Recommendation is exactly what an experienced LATAM founder would say. Garbage/no-pain/saturated → discard. Real pain + clear ICP + addressable market → promote. Ambiguous → wait. |
| 4 | Recommendation is defensible but borderline — could justify either way |
| 3 | Recommendation is in the wrong tier (e.g., should be `wait` but says `promote`) but the reasoning shows partial understanding |
| 2 | Recommendation contradicts evidence (e.g., says `promote` on a movie review or recipe) |
| 1 | Recommendation is invalid (not one of the 3 allowed values) or actively harmful |

**Red flags:** Always-promote bias; ignoring obvious garbage (theme="test"); recommending promote on saturated markets without a differentiator.

**Green flags:** Discards off-topic content (recipes, news), waits on too-vague ideas, promotes only when ICP + market are both estimable.

## Criterion 2: Market Estimate Specificity (1–5)

Evaluates `market_size_estimate` — should be a concrete range, not a hand-wave.

| Score | Description |
|-------|-------------|
| 5 | Cites a numeric range with units AND geographic scope ("~50k empresas LATAM", "$2B TAM regional", "Nicho pequeño <1k usuarios") |
| 4 | Has a number but missing geographic context, OR has scope but no number |
| 3 | Qualitative ("mercado grande", "nicho") with no number |
| 2 | Generic ("oportunidad importante") with no specifics |
| 1 | Empty, contradictory, or obviously fabricated number |

**Red flags:** "Millones de usuarios" with no methodology; copy-paste TAM from a different industry.

**Green flags:** Country-specific data points; segmented numbers (e.g., "20k empresas con ≥50 empleados en Ecuador").

## Criterion 3: ICP Probable Specificity (1–5)

Evaluates `icp_probable` — the customer profile the agent inferred.

| Score | Description |
|-------|-------------|
| 5 | Names a role + company size + region ("CFO de PYMEs 20-200 empleados en Ecuador/Colombia") |
| 4 | Has 2 of those 3 dimensions |
| 3 | Has 1 dimension only |
| 2 | Generic ("empresas que necesitan X") |
| 1 | Empty or contradicts the signal context |

**Red flags:** "Cualquier empresa interesada en eficiencia"; ICPs that span B2B + B2C + government.

**Green flags:** Concrete title (CFO, COO, gerente de planta) + company-size band + country.

## Criterion 4: Risks Identification (1–5)

Evaluates `risks` list — should capture the 2-3 things most likely to kill the idea.

| Score | Description |
|-------|-------------|
| 5 | 2-3 specific, distinct risks naming real failure modes (CAC>LTV, regulatory, integration complexity, etc.) |
| 4 | 2-3 risks but one is generic ("competition") |
| 3 | Only 1-2 specific risks, or 3 but mostly generic |
| 2 | Risks are all generic / boilerplate ("market may not adopt") |
| 1 | Empty list, OR contradicts the rest of the analysis ("riesgo: ninguno") |

**Red flags:** "Market risk" / "execution risk" with no specificity; identical risks for unrelated ideas.

**Green flags:** Risks specific to LATAM context (regulation changes, currency volatility, distribution channel concentration), or to the specific business model.

## Criterion 5: Reasoning Coherence (1–5)

Evaluates `reasoning` — does it tie together market + ICP + recommendation logically?

| Score | Description |
|-------|-------------|
| 5 | 1-2 sentences that clearly justify the recommendation using market + ICP signals. A founder can read it and instantly agree or push back |
| 4 | Reasoning is correct but underdeveloped (e.g., just restates the recommendation) |
| 3 | Reasoning is generic ("good opportunity in LATAM") without tying to the analysis fields |
| 2 | Reasoning contradicts the recommendation or the market/ICP estimates |
| 1 | Empty or off-topic ("see analysis above") |

**Red flags:** Reasoning copy-pasted from training data; circular ("Recommend promote because it's promotable").

**Green flags:** "Promote: ICP is bookable via LinkedIn, market is ≥10k orgs, and the differentiator (X) is not commoditized yet."

## Aggregate Decision Matrix

After computing per-criterion scores:

| Overall | Action |
|---|---|
| ≥ 4.0 | Trust the recommendation. Surface it as confident in the dashboard. |
| 3.0–3.9 | Surface with a "moderate confidence" tag. Founder reviews before promoting. |
| 2.0–2.9 | Re-run analyze with a sharpened prompt (different temperature or model). |
| < 2.0 | Flag the signal for human triage; don't show the analysis. |

## What this rubric does NOT cover

- **Cost** — that's already capped per-call (~$0.005)
- **Latency** — handled by infrastructure
- **Format validity** — covered by `tests/test_idea_analyzer.py` (schema, types, valid recommendation enum)
- **Multi-LLM agreement** — IdeaAnalyzer is single-LLM by design (cheap triage); cross-LLM agreement only applies to `gate_decider`

## When to revisit this rubric

- When ≥30% of promoted signals get `kill` from `gate_decider` (signals analyzer is over-confident → tighten criterion 1)
- When the founder consistently overrides `promote` → `wait` (criterion 1 calibration is off)
- After M4 outcome data lets us correlate analyzer.recommendation with actual conversion (real ground truth)
