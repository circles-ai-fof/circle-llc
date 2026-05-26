# Rubric: Gate Decision Quality — gate_decider

Evaluates outputs from `gate_decider` (GateDecision: pass/kill/iterate).

## Usage

Score each criterion from 1 to 5. Compute `overall = mean(4 criteria)`.
A score ≥ 3.5 overall is considered acceptable. A score < 2.5 overall indicates poor decision quality.

---

## Criterion 1: Evidence Alignment (1–5)

Evaluates whether the **verdict** (pass/kill/iterate) is correctly supported by the metrics provided.

| Score | Description |
|-------|-------------|
| 5 | Verdict is unambiguously correct: clear PASS on strong metrics, clear KILL on failed metrics, ITERATE on mixed. Threshold references are explicit (e.g., "CTR 4.5% vs 2% target") |
| 4 | Verdict is correct but one metric contradicts it without explanation |
| 3 | Verdict is defensible but a reasonable analyst would choose a different verdict |
| 2 | Verdict contradicts the majority of metrics (e.g., PASS with 0 conversions) |
| 1 | Verdict is clearly wrong or random — no alignment with data |

**Reference thresholds** (from EvidenceTestDesign targets):
- CTR: target_ctr from the test design
- CVR: target_conversion_rate from the test design
- CAC: cost_per_conversion vs expected LTV

**Edge cases:**
- Very few impressions (<500): verdict should acknowledge insufficient data, confidence should be < 0.5
- Data anomaly (conversions > clicks): verdict should flag data quality issue

---

## Criterion 2: Confidence Calibration (1–5)

Evaluates whether the `confidence` score (0.0–1.0) is appropriately calibrated.

| Score | Description |
|-------|-------------|
| 5 | Confidence perfectly matches signal strength: high (>0.8) for clear signals, moderate (0.4–0.7) for mixed, low (<0.4) for insufficient data |
| 4 | Confidence is in the right range but slightly over/under-confident by ≤0.15 |
| 3 | Confidence is in a reasonable range but off by >0.15 (e.g., 0.8 for a borderline case) |
| 2 | Confidence is systematically wrong in direction (e.g., 0.9 for a data anomaly) |
| 1 | Confidence is 0 or 1 when data is ambiguous, or confidence does not vary across cases |

**Calibration guidelines:**

| Situation | Expected Confidence Range |
|-----------|--------------------------|
| All metrics beat targets by >50% | 0.80 – 0.95 |
| All metrics beat targets by 0–50% | 0.65 – 0.80 |
| Mixed metrics (some above, some below) | 0.40 – 0.65 |
| All metrics below targets | 0.70 – 0.90 (confident KILL) |
| <500 impressions total | 0.20 – 0.45 |
| Data anomaly detected | 0.10 – 0.35 |

---

## Criterion 3: Rationale Quality (1–5)

Evaluates whether the `rationale` is **specific, data-driven, and actionable**.

| Score | Description |
|-------|-------------|
| 5 | Rationale cites specific numbers from metrics, compares to targets, explains the business implication (e.g., "CAC $12 gives LTV/CAC > 5 at $60/mo ACV, viable unit economics") |
| 4 | Rationale is data-specific but lacks business implication or forward-looking interpretation |
| 3 | Rationale is generic ("metrics are good" / "metrics are bad") without specific numbers |
| 2 | Rationale restates the verdict without explaining why ("we should pass because the test passed") |
| 1 | Rationale is empty, generic filler, or contradicts the verdict |

**Red flags:**
- "The metrics look promising" (no numbers)
- "Based on our analysis" (no actual analysis)
- Rationale that would apply to any decision regardless of metrics

**Green flags:**
- "CTR 4.5% exceeds 2% target by 2.25x"
- "Zero conversions despite 32 clicks signals no product-market fit at $10 price point"
- "CAC $147 is unsustainable at $30/month ACV — needs 5-month payback"

---

## Criterion 4: Next Steps Actionability (1–5)

Evaluates whether `next_steps` are **concrete, specific, and appropriate** for the verdict.

| Score | Description |
|-------|-------------|
| 5 | Next steps are specific, time-bound, and directly address the verdict's implications. PASS → build next, KILL → archive + pivot, ITERATE → specific experiment to run |
| 4 | Next steps are appropriate but one is generic ("continue testing") |
| 3 | Next steps are mostly generic action items not specifically tied to this idea/metrics |
| 2 | Next steps are too broad, contradictory to the verdict, or impractical |
| 1 | No next steps, or all steps are generic ("investigate further") |

**Verdict-appropriate next steps:**

| Verdict | Expected Next Step Types |
|---------|--------------------------|
| PASS | MVP development scope, team allocation, budget, launch timeline |
| KILL | Archive rationale, alternative idea directions, learnings documented |
| ITERATE | Specific hypothesis to change (price? copy? channel?), re-test parameters |

---

## Scoring Procedure

```
overall = (evidence_alignment + confidence_calibration + rationale_quality + next_steps_actionability) / 4
```

### Interpretation

| Overall Score | Interpretation | Action |
|--------------|----------------|--------|
| 4.5 – 5.0 | Exceptional decision quality | No action required |
| 3.5 – 4.4 | Good decision — trust the verdict | No action required |
| 2.5 – 3.4 | Borderline — human review recommended | Flag for founder review |
| 1.5 – 2.4 | Poor decision quality — regenerate | Retry with CoT prompt |
| 1.0 – 1.4 | Fail — wrong verdict or no evidence | Escalate to human |

---

## Example Scorings

### Example A: Strong PASS

**Input metrics:** impressions=12000, clicks=480, conversions=38, CTR=4.0%, CVR=7.9%, CAC=$12.63
**Output:** verdict=pass, confidence=0.87

| Criterion | Score | Justification |
|-----------|-------|---------------|
| Evidence Alignment | 5 | CTR 4.0% vs 2.5% target, CVR 7.9% vs 5% target — both exceeded |
| Confidence Calibration | 5 | 0.87 is appropriate for metrics beating targets by 50-70% |
| Rationale Quality | 5 | "CTR 4.5% exceeds 2% target. CVR 10% well above 3% threshold. CAC $4.44 highly viable" |
| Next Steps Actionability | 4 | "Proceed to MVP build, allocate $5K seed budget" — good but lacks timeline |
| **Overall** | **4.75** | **Exceptional** |

---

### Example B: KILL with Zero Conversions

**Input metrics:** impressions=8000, clicks=32, conversions=0, CTR=0.4%, CVR=0%
**Output:** verdict=kill, confidence=0.92

| Criterion | Score | Justification |
|-----------|-------|---------------|
| Evidence Alignment | 5 | Zero conversions despite 32 clicks = no PMF signal at this price |
| Confidence Calibration | 4 | 0.92 is slightly high — could be 0.85 to leave room for copy A/B |
| Rationale Quality | 5 | "CTR 0.4% far below 2% target. Zero conversions after 32 clicks signals no product-market fit" |
| Next Steps Actionability | 4 | "Archive idea, pivot to adjacent problem" — good direction, needs specifics |
| **Overall** | **4.5** | **Strong decision** |

---

### Example C: Insufficient Data Edge Case

**Input metrics:** impressions=180, clicks=5, conversions=1, CTR=2.8%
**Expected:** verdict should acknowledge insufficient data, confidence < 0.5

| Criterion | Score | Justification |
|-----------|-------|---------------|
| Evidence Alignment | 5 | Correctly identifies insufficient data — can't conclude PMF from 180 impressions |
| Confidence Calibration | 5 | confidence=0.3 appropriately low for tiny sample |
| Rationale Quality | 4 | Mentions sample size but doesn't calculate statistical power needed |
| Next Steps Actionability | 5 | "Run test with ≥1000 impressions, allocate $200 minimum for Facebook ads" |
| **Overall** | **4.75** | **Correctly handles edge case** |
