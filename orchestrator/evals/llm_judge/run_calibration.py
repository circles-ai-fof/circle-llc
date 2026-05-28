"""
LLM-judge calibration runner.
- gate_decider: deterministic Python rules (metrics are objective)
- idea_hunter / idea_maturer: LLM judge with few-shot examples
Target: >=80% agreement.
"""
import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent.parent
DATASET = ROOT / "orchestrator/evals/llm_judge/calibration_dataset.jsonl"

LABEL_MAP = {
    "pass": "pass", "kill": "kill", "iterate": "iterate",
    "good_idea": "good", "ok_idea": "ok", "bad_idea": "bad",
    "good_maturation": "good", "ok_maturation": "ok", "bad_maturation": "bad",
    # idea_analyzer labels (identity-mapped — already in canonical form)
    "promote": "promote", "wait_for_more_data": "wait_for_more_data", "discard": "discard",
}

# ──────────────────────────────────────────────
# DETERMINISTIC GATE JUDGE
# Applied in priority order. Matches human labeling logic from rubric.
# ──────────────────────────────────────────────
def _deterministic_gate_verdict(ex: dict) -> str:
    inp = ex["input"]
    metrics = inp.get("metrics", {})
    design = inp.get("test_design", {})

    impressions = metrics.get("impressions", 0)
    clicks = metrics.get("clicks", 0)
    conversions = metrics.get("conversions", 0)
    ctr = metrics.get("ctr", 0.0)
    cvr = metrics.get("conversion_rate", 0.0)
    target_ctr = design.get("target_ctr", 0.025)
    target_cvr = design.get("target_conversion_rate", 0.05)

    # 1. PASS — both metrics above target with sufficient data
    if (
        impressions >= 500
        and ctr >= target_ctr
        and cvr >= target_cvr
    ):
        return "pass"

    # 2. KILL — hard signals: no conversions AND very low CTR AND enough data
    if (
        impressions >= 1000
        and conversions == 0
        and ctr < target_ctr / 2.5
    ):
        return "kill"

    # 3. KILL — CTR far below target even with some conversions (large enough sample)
    if (
        impressions >= 2000
        and ctr < target_ctr / 4
        and cvr < target_cvr / 3
    ):
        return "kill"

    # 4. KILL — CTR < 30% of target with large sample (clear no-interest signal)
    if impressions >= 10000 and ctr < target_ctr * 0.3:
        return "kill"

    # 4. ITERATE — everything else (mixed signals, borderline, insufficient data)
    return "iterate"


# ──────────────────────────────────────────────
# LLM IDEA JUDGE — with few-shot examples
# ──────────────────────────────────────────────
FEW_SHOT_SYSTEM = """You are a calibrated idea quality judge. Classify AI-generated startup ideas as: good, ok, or bad.

SCORING GUIDE:
- good (score 4-5): Specific problem with numbers/evidence, hyper-specific market (role+size+geo), differentiated solution, credible unfair advantage, concrete risks
- ok (score 2.5-3.9): Recognizable problem but vague, market defined but too broad, solution is plausible, risks are generic
- bad (score 1-2.4): Generic problem ("companies need efficiency"), undefined market, no differentiation, buzzword-heavy

EXAMPLES (calibrated against human judges):
---
GOOD: {"title":"FacturAI EC","problem_statement":"60% PYMEs Ecuador esperan 90+ días cobrar facturas, destruyendo capital de trabajo","target_market":"CFO/dueño PYME 10-50 empleados, Ecuador, sector manufactura y servicios","proposed_solution":"Anticipo de facturas en 24h vía plataforma digital con scoring SAT/SRI","unfair_advantage":"Integración directa API SRI Ecuador — ningún competidor la tiene"}
LABEL: good

OK: {"title":"App Salud","problem_statement":"Las personas necesitan acceder a servicios de salud más fácilmente","target_market":"Adultos en LATAM que usan smartphones","proposed_solution":"Aplicación para agendar citas médicas online"}
LABEL: ok

BAD: {"title":"Plataforma Digital","problem_statement":"Las empresas quieren ser más productivas y eficientes","target_market":"Todas las empresas que quieren crecer","proposed_solution":"Solución integral de productividad empresarial con IA"}
LABEL: bad
---

Reply with EXACTLY one word: good, ok, or bad."""


def _llm_idea_verdict(client: anthropic.Anthropic, ex: dict) -> str:
    out = ex["output"]
    # Flatten the output to a compact string for the judge
    if isinstance(out, dict):
        summary = json.dumps(out, ensure_ascii=False)[:600]
    else:
        summary = str(out)[:600]

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5,
        system=[{
            "type": "text",
            "text": FEW_SHOT_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": f"Classify this output:\n{summary}"}],
    )
    raw = resp.content[0].text.strip().lower().split()[0]
    return raw if raw in {"good", "ok", "bad"} else "unknown"


# ──────────────────────────────────────────────
# IDEA ANALYZER — runs the actual agent (single Haiku call) and returns
# the recommendation value to compare against the human label.
# ──────────────────────────────────────────────
def _run_idea_analyzer(client: anthropic.Anthropic, ex: dict) -> str:
    """Execute IdeaAnalyzerAgent on the test case and return its recommendation."""
    from orchestrator.agents.idea_analyzer import IdeaAnalyzerAgent
    agent = IdeaAnalyzerAgent(mock_mode=False, client=client)
    inp = ex["input"]
    try:
        result = agent.analyze(
            theme=inp["theme"],
            excerpt=inp["excerpt"],
            suggested_topic=inp["suggested_topic"],
        )
        return result.recommendation
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR running idea_analyzer on {ex['id']}: {exc}")
        return "error"


def main() -> int:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return 1
    client = anthropic.Anthropic(api_key=key)

    examples = [
        json.loads(ln)
        for ln in DATASET.read_text(encoding="utf-8").strip().splitlines()
    ]
    agree, total = 0, 0
    mismatches = []

    for ex in examples:
        human = LABEL_MAP.get(ex["human_label"], ex["human_label"])
        agent = ex["agent"]

        if agent == "gate_decider":
            llm = _deterministic_gate_verdict(ex)
        elif agent == "idea_analyzer":
            llm = _run_idea_analyzer(client, ex)
        else:
            llm = _llm_idea_verdict(client, ex)

        match = human == llm
        if match:
            agree += 1
        else:
            mismatches.append({"id": ex["id"], "human": human, "llm": llm, "agent": agent})
        total += 1
        status = "OK" if match else "XX"
        print(f"  {ex['id']:12s}  [{agent:14s}]  human={human:8s}  llm={llm:8s}  {status}")

    pct = agree / total * 100
    print(f"\n{'='*65}")
    print(f"Agreement: {agree}/{total} = {pct:.1f}%")
    print(f"Target:    >=80%  |  Status: {'PASS' if pct >= 80 else 'FAIL'} ({pct:.1f}%)")

    if mismatches:
        print(f"\nMismatches ({len(mismatches)}):")
        for m in mismatches:
            print(f"  {m['id']:12s}  [{m['agent']:14s}]  human={m['human']}  llm={m['llm']}")

    # Persist results
    results_path = ROOT / "orchestrator/evals/llm_judge/calibration_results.json"
    results = {
        "agreement_pct": round(pct, 1),
        "agree": agree,
        "total": total,
        "target_met": pct >= 80,
        "gate_method": "deterministic_python",
        "idea_method": "llm_sonnet_few_shot",
        "idea_analyzer_method": "agent_invocation_haiku",
        "mismatches": mismatches,
    }
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {results_path.name}")

    return 0 if pct >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
