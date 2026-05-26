# Rubric: Idea Quality — idea_hunter & idea_maturer

Evaluates outputs from `idea_hunter` (IdeaSpec) and `idea_maturer` (MatureIdeaSpec).

## Usage

Score each criterion from 1 to 5. Compute `overall = mean(all criteria)`.
A score ≥ 3.5 overall is considered acceptable. A score < 2.5 overall should trigger a retry or flag.

## Criterion 1: Problem Clarity (1–5)

Evaluates whether the problem statement identifies a **real, specific, painful** problem.

| Score | Description |
|-------|-------------|
| 5 | Problem is crystal clear, quantified ("60% PYMEs wait 60+ days"), specific to a segment, and clearly painful |
| 4 | Problem is clear and specific, but lacks quantification or some specificity |
| 3 | Problem is identifiable but stated at too high a level ("companies have inefficiencies") |
| 2 | Problem is vague or generic — could apply to any industry/segment |
| 1 | No clear problem, or problem is trivially false / fabricated |

**Red flags:** "companies want to be more productive", "people need better tools", buzzword-only problems.

**Green flags:** Numbers, specific roles affected, frequency/severity of occurrence.

---

## Criterion 2: Market Specificity (1–5)

Evaluates whether the `target_market` is actionable — can you run an ad campaign to this audience?

| Score | Description |
|-------|-------------|
| 5 | Market is hyper-specific: role + company size + geography + industry (e.g., "CFO PYMEs 10-50 employees, Ecuador, manufacturing") |
| 4 | Market has 3 of 4 dimensions: good enough for ad targeting |
| 3 | Market has 2 dimensions (e.g., "SMBs in LATAM") — too broad for efficient targeting |
| 2 | Market is one dimension ("empresas") or uses demographic proxy without context |
| 1 | Market is "everyone", "all people", or undefined |

**Red flags:** "toda la población LATAM", "empresas que quieren crecer", English + Spanish market mixed without explanation.

**Green flags:** LinkedIn-targetable audiences, specific country, specific company size, specific job title.

---

## Criterion 3: Solution Differentiation (1–5)

Evaluates how well the proposed solution stands out from existing alternatives.

| Score | Description |
|-------|-------------|
| 5 | Solution is demonstrably unique: specific mechanism, unfair advantage, moat identified |
| 4 | Solution has a clear differentiator but it could be copied within 3–6 months |
| 3 | Solution is a feature improvement ("like X but cheaper/faster") — no structural moat |
| 2 | Solution is a generic description of the category ("an app that helps with X") |
| 1 | Solution is a direct copy of an existing product, impossible to execute, or harmful |

**Red flags:** "like Rappi but better", "like Coursera but in Spanish", "blockchain-based everything".

**Green flags:** Regulatory moat, network effect, proprietary data, exclusive partnerships, tech patent.

---

## Criterion 4: ICP Definition (1–5)

*(Only for idea_maturer outputs — MatureIdeaSpec.icp)*

Evaluates whether the Ideal Customer Profile is concrete enough to guide acquisition.

| Score | Description |
|-------|-------------|
| 5 | ICP has: demographic (age/role/company), psychographic (motivation/fear), pain_points (≥2 specific), willingness_to_pay (range), acquisition_channel (specific platform) |
| 4 | ICP has all 5 fields but one is generic (e.g., acquisition_channel = "social media") |
| 3 | ICP has 3–4 fields filled but with low specificity |
| 2 | ICP has 1–2 fields filled or all fields are vague |
| 1 | ICP is missing or says "everyone" / "all users" |

**Note:** For idea_hunter outputs (IdeaSpec), skip this criterion and use the 4-criterion mean.

**Red flags:** willingness_to_pay = "depends", acquisition_channel = "all channels", pain_points = ["generic problem"].

**Green flags:** Willingness_to_pay with a specific dollar range, specific platform (LinkedIn, Facebook grupos, WhatsApp), pain points with frequency/severity.

---

## Criterion 5: Risk Awareness (1–5)

Evaluates whether key_risks identifies **plausible, material risks** that could kill the business.

| Score | Description |
|-------|-------------|
| 5 | Lists ≥3 specific risks: regulatory (specific law), competitive (specific competitor), operational (specific bottleneck), with implied mitigation awareness |
| 4 | Lists 2–3 good risks but lacks specificity on one (e.g., "competition" without naming it) |
| 3 | Lists 1–2 risks that are real but obvious / surface-level |
| 2 | Lists generic risks ("market risk", "technology risk") or only one risk |
| 1 | No risks listed, or risks are copied from a template without relevance |

**Red flags:** key_risks = ["competition"], key_risks = ["might not work"], single-item risk lists.

**Green flags:** Named regulatory bodies (BCE, SBS Peru, CNBV Mexico), named competitors, specific technical constraints.

---

## Scoring Procedure

```
For idea_hunter outputs (IdeaSpec):
  Use criteria 1, 2, 3, 5 (skip ICP criterion)
  overall = (c1 + c2 + c3 + c5) / 4

For idea_maturer outputs (MatureIdeaSpec):
  Use all 5 criteria
  overall = (c1 + c2 + c3 + c4 + c5) / 5
```

### Interpretation

| Overall Score | Interpretation | Action |
|--------------|----------------|--------|
| 4.5 – 5.0 | Exceptional idea output | No action required |
| 3.5 – 4.4 | Good — proceed to market validation | No action required |
| 2.5 – 3.4 | Borderline — flag for human review | Human review before proceeding |
| 1.5 – 2.4 | Poor — regenerate with more specific context | Retry with enhanced prompt |
| 1.0 – 1.4 | Fail — likely injection or garbage input | Log and discard |

---

## Example Scoring

**Idea:** "FacturaPago EC — Plataforma factoring digital para PYMEs ecuatorianas"

| Criterion | Score | Justification |
|-----------|-------|---------------|
| Problem Clarity | 5 | "60% PYMEs espera 60+ días cobro facturas" — quantified, specific segment |
| Market Specificity | 5 | "PYMEs manufactureras Ecuador 10-50 empleados" — LinkedIn-targetable |
| Solution Differentiation | 4 | Marketplace factoring is clear, but lacks regulatory moat detail |
| ICP Definition | 5 | Full ICP with $200-500/mes WTP, LinkedIn acquisition channel |
| Risk Awareness | 4 | BCE regulation named, but morosidad risk needs more detail |
| **Overall** | **4.6** | **Proceed to market validation** |
