"use client";

import { useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type RunResponse = {
  run_id: string;
  status: string;
  idea_title: string;
  verdict: "pass" | "kill" | "iterate";
  confidence: number;
  rationale: string;
  next_steps: string[];
  landing_headline: string;
  landing_slug: string;
  test_design: {
    hypothesis: string;
    ad_budget_usd: number;
    test_duration_days: number;
    target_ctr: number;
    target_conversion_rate: number;
  };
  canonical_goal_statement: string;
  steps_used: number;
  cost_usd_estimated: number;
  needs_human_review: boolean;
  review_reason: string | null;
  ensemble_votes: string[] | null;
};

type Agent = {
  key: string;
  number: string;
  name: string;
  emoji: string;
  description: string;
};

const AGENTS: Agent[] = [
  {
    key: "idea_hunter",
    number: "1",
    name: "Cazador de ideas",
    emoji: "🎯",
    description: "Genera UNA idea concreta desde tu topic",
  },
  {
    key: "idea_enricher",
    number: "1.5",
    name: "Refinador",
    emoji: "🔍",
    description: "Puntúa especificidad, sharpens si es vaga, opcionalmente web_search",
  },
  {
    key: "idea_maturer",
    number: "2",
    name: "Madurador",
    emoji: "🧠",
    description: "Define ICP + value proposition + riesgos",
  },
  {
    key: "market_validator",
    number: "3",
    name: "Validador",
    emoji: "📊",
    description: "Diseña el test de mercado (presupuesto, días, métricas)",
  },
  {
    key: "landing_generator",
    number: "4a",
    name: "Copywriter",
    emoji: "✍️",
    description: "Genera headline + value props + CTA",
  },
  {
    key: "gate_decider",
    number: "4b",
    name: "Juez",
    emoji: "⚖️",
    description: "Ensemble Claude+GPT+Gemini → PASS/KILL/ITERATE",
  },
];

const verdictColors = {
  pass: { bg: "rgba(0,229,160,0.1)", border: "#00E5A0", color: "#00E5A0" },
  kill: { bg: "rgba(255,68,68,0.1)", border: "#FF4444", color: "#FF4444" },
  iterate: { bg: "rgba(255,184,0,0.1)", border: "#FFB800", color: "#FFB800" },
};

export default function CazarPage() {
  const [topic, setTopic] = useState("");
  const [secret, setSecret] = useState("");
  const [running, setRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1); // index in AGENTS
  const [result, setResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number>(0);

  // While running, animate through agents
  useEffect(() => {
    if (!running) return;
    let step = 0;
    setCurrentStep(0);
    const id = setInterval(() => {
      step += 1;
      if (step < AGENTS.length) setCurrentStep(step);
      else clearInterval(id);
    }, 5500); // ~5.5s per agent visual; actual call may be faster or slower
    return () => clearInterval(id);
  }, [running]);

  const handleRun = async () => {
    if (!topic.trim()) return;
    setError(null);
    setResult(null);
    setRunning(true);
    startedAt.current = Date.now();

    try {
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (secret) headers["X-Gate-Secret"] = secret;
      const res = await authFetch("/api/v1/gate/run", {
        method: "POST",
        headers,
        body: JSON.stringify({ topic: topic.trim() }),
        signal: AbortSignal.timeout(120_000),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch {
          /* not json */
        }
        throw new Error(detail);
      }
      const data = (await res.json()) as RunResponse;
      setResult(data);
      setCurrentStep(AGENTS.length); // all done
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setError(null);
    setCurrentStep(-1);
    setTopic("");
  };

  const elapsed = result && startedAt.current
    ? ((Date.now() - startedAt.current) / 1000).toFixed(1)
    : null;

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          🎯 Cazar idea
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Lanza el workflow completo de 6 agentes para una idea. Cada ejecución cuesta ~$0.06 USD.
        </p>
      </header>

      {/* Input */}
      {!result && (
        <section
          style={{
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            padding: 24,
            marginBottom: 20,
          }}
        >
          <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 8 }}>
            Topic / tendencia / problema (puede ser vago, el refinador lo sharpens)
          </label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Ej: plataforma para gestionar inventario en restaurantes pequeños LATAM"
            rows={3}
            maxLength={300}
            disabled={running}
            style={{
              width: "100%",
              padding: 14,
              background: "#0B0F1A",
              color: "#fff",
              border: "1px solid #1e293b",
              borderRadius: 8,
              fontSize: 14,
              fontFamily: "inherit",
              resize: "vertical",
              outline: "none",
              opacity: running ? 0.5 : 1,
            }}
          />
          <div style={{ marginTop: 12, marginBottom: 16 }}>
            <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
              X-Gate-Secret (si el backend lo requiere — opcional)
            </label>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="GATE_RUN_SECRET de Railway"
              disabled={running}
              style={{
                width: "100%",
                padding: 10,
                background: "#0B0F1A",
                color: "#fff",
                border: "1px solid #1e293b",
                borderRadius: 6,
                fontSize: 13,
                fontFamily: "monospace",
              }}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={!topic.trim() || running}
            style={{
              padding: "12px 24px",
              background: "#00D4FF",
              color: "#0B0F1A",
              border: "none",
              borderRadius: 8,
              fontWeight: 700,
              fontSize: 14,
              cursor: !topic.trim() || running ? "not-allowed" : "pointer",
              opacity: !topic.trim() || running ? 0.5 : 1,
            }}
          >
            {running ? "Cazando…" : "🎯 Cazar idea"}
          </button>
        </section>
      )}

      {/* Agents pipeline */}
      {(running || result || error) && (
        <section
          style={{
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            padding: 24,
            marginBottom: 20,
          }}
        >
          <h2 style={{ color: "#fff", fontSize: 16, fontWeight: 600, marginBottom: 16 }}>
            Pipeline de agentes
          </h2>
          <div style={{ display: "grid", gap: 8 }}>
            {AGENTS.map((agent, i) => {
              const status =
                error && i === currentStep
                  ? "error"
                  : i < currentStep
                    ? "done"
                    : i === currentStep && running
                      ? "active"
                      : i === currentStep && result
                        ? "done"
                        : "pending";
              return <AgentRow key={agent.key} agent={agent} status={status} />;
            })}
          </div>
        </section>
      )}

      {/* Error */}
      {error && (
        <div
          style={{
            background: "rgba(255,68,68,0.1)",
            border: "1px solid rgba(255,68,68,0.3)",
            borderRadius: 12,
            padding: 16,
            marginBottom: 20,
            color: "#FF4444",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Error</div>
          <div style={{ fontSize: 13 }}>{error}</div>
          <button
            onClick={handleReset}
            style={{
              marginTop: 12,
              padding: "6px 14px",
              background: "transparent",
              color: "#FF4444",
              border: "1px solid #FF4444",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Intentar de nuevo
          </button>
        </div>
      )}

      {/* Result */}
      {result && <ResultView result={result} elapsed={elapsed} onReset={handleReset} />}
    </main>
  );
}

function AgentRow({
  agent,
  status,
}: {
  agent: Agent;
  status: "pending" | "active" | "done" | "error";
}) {
  const colors = {
    pending: { bg: "#0B0F1A", border: "#1e293b", text: "#475569" },
    active: { bg: "rgba(0,212,255,0.1)", border: "#00D4FF", text: "#fff" },
    done: { bg: "rgba(0,229,160,0.06)", border: "#00E5A030", text: "#cbd5e1" },
    error: { bg: "rgba(255,68,68,0.06)", border: "#FF444430", text: "#FF4444" },
  }[status];

  const indicator = {
    pending: "○",
    active: "●",
    done: "✓",
    error: "✗",
  }[status];

  return (
    <div
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        borderRadius: 8,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 14,
        transition: "all 0.3s ease",
      }}
    >
      <span
        style={{
          color: colors.border,
          fontSize: 16,
          fontFamily: "monospace",
          width: 18,
          textAlign: "center",
          animation: status === "active" ? "pulse 1s infinite" : "none",
        }}
      >
        {indicator}
      </span>
      <span style={{ fontSize: 20 }}>{agent.emoji}</span>
      <span style={{ color: "#64748b", fontSize: 11, fontFamily: "monospace", width: 36 }}>
        Step {agent.number}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ color: colors.text, fontSize: 14, fontWeight: 600 }}>{agent.name}</div>
        <div style={{ color: "#64748b", fontSize: 12 }}>{agent.description}</div>
      </div>
      <style>{`@keyframes pulse { 50% { opacity: 0.4 } }`}</style>
    </div>
  );
}

function ResultView({
  result,
  elapsed,
  onReset,
}: {
  result: RunResponse;
  elapsed: string | null;
  onReset: () => void;
}) {
  const verdict = result.verdict;
  const colors = verdictColors[verdict];
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Verdict banner */}
      <div
        style={{
          background: colors.bg,
          border: `1px solid ${colors.border}`,
          borderRadius: 12,
          padding: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ color: colors.color, fontSize: 32, fontWeight: 900, letterSpacing: 1 }}>
            {verdict.toUpperCase()}
          </span>
          <span style={{ color: colors.color, fontSize: 28, fontWeight: 700 }}>
            {Math.round(result.confidence * 100)}%
          </span>
        </div>
        <p style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.5 }}>{result.rationale}</p>
        {result.needs_human_review && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: "rgba(255,184,0,0.1)",
              border: "1px solid #FFB80050",
              borderRadius: 8,
              color: "#FFB800",
              fontSize: 13,
            }}
          >
            ⚠️ Este run requiere revisión humana (ensemble disagreement).{" "}
            <a href="/revision" style={{ color: "#FFB800", textDecoration: "underline" }}>
              Ir a Revisión →
            </a>
          </div>
        )}
      </div>

      {/* Idea card */}
      <Card title="🎯 Idea generada">
        <h3 style={{ color: "#fff", fontSize: 18, fontWeight: 700, marginBottom: 8 }}>
          {result.idea_title}
        </h3>
        <div style={{ color: "#94a3b8", fontSize: 13, marginBottom: 12 }}>
          Goal: <span style={{ color: "#cbd5e1" }}>{result.canonical_goal_statement}</span>
        </div>
      </Card>

      {/* Test design */}
      <Card title="📊 Test propuesto (14 días)">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
          <Stat label="Budget" value={`$${result.test_design.ad_budget_usd}`} />
          <Stat label="Duración" value={`${result.test_design.test_duration_days}d`} />
          <Stat label="Target CTR" value={`${(result.test_design.target_ctr * 100).toFixed(1)}%`} />
          <Stat label="Target CVR" value={`${(result.test_design.target_conversion_rate * 100).toFixed(1)}%`} />
        </div>
        <div style={{ marginTop: 12, color: "#94a3b8", fontSize: 13 }}>
          <strong style={{ color: "#cbd5e1" }}>Hipótesis:</strong> {result.test_design.hypothesis}
        </div>
      </Card>

      {/* Landing */}
      <Card title="✍️ Landing generado">
        <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Headline</div>
        <h3 style={{ color: "#fff", fontSize: 18, fontWeight: 600, marginBottom: 16 }}>
          {result.landing_headline}
        </h3>
        <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Slug</div>
        <code style={{ color: "#00D4FF", fontSize: 14, fontFamily: "monospace" }}>
          /f/{result.landing_slug}
        </code>
      </Card>

      {/* Ensemble votes */}
      {result.ensemble_votes && result.ensemble_votes.length > 0 && (
        <Card title="🗳️ Votos del ensemble (Claude + GPT + Gemini)">
          <div style={{ display: "grid", gap: 6 }}>
            {result.ensemble_votes.map((v, i) => (
              <div key={i} style={{ color: "#cbd5e1", fontSize: 13, fontFamily: "monospace" }}>
                • {v}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Next steps */}
      <Card title="→ Siguientes pasos">
        <ul style={{ paddingLeft: 20, color: "#cbd5e1", fontSize: 14, lineHeight: 1.7 }}>
          {result.next_steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </Card>

      {/* Footer stats */}
      <div
        style={{
          display: "flex",
          gap: 16,
          padding: 16,
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          color: "#64748b",
          fontSize: 12,
          fontFamily: "monospace",
          flexWrap: "wrap",
        }}
      >
        <span>run_id: {result.run_id}</span>
        <span>·</span>
        <span>steps: {result.steps_used}/20</span>
        <span>·</span>
        <span>cost: ${result.cost_usd_estimated.toFixed(4)}</span>
        {elapsed && (
          <>
            <span>·</span>
            <span>elapsed: {elapsed}s</span>
          </>
        )}
      </div>

      <button
        onClick={onReset}
        style={{
          padding: "12px 24px",
          background: "transparent",
          color: "#94a3b8",
          border: "1px solid #1e293b",
          borderRadius: 8,
          fontSize: 14,
          cursor: "pointer",
        }}
      >
        🎯 Cazar otra idea
      </button>
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: 20,
      }}
    >
      <h3 style={{ color: "#94a3b8", fontSize: 11, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 12 }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "#0B0F1A", borderRadius: 8, padding: 12 }}>
      <div style={{ color: "#64748b", fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color: "#fff", fontSize: 18, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
