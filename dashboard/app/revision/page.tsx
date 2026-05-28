"use client";

import { useEffect, useState } from "react";
import VerdictBadge from "@/components/VerdictBadge";
import { authFetch } from "@/lib/auth";

type PendingItem = {
  run_id: string;
  idea_title: string;
  verdict: string;
  confidence: number;
  review_reason: string;
  ensemble_votes: string[];
  rationale: string;
};

type Pending = { pending_count: number; items: PendingItem[] };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

// Demo data — used when API is unreachable so the page never goes blank
const DEMO: Pending = {
  pending_count: 2,
  items: [
    {
      run_id: "demo-1a2b3c4d-5e6f-7890-1234-567890abcdef",
      idea_title: "TechPulse LATAM",
      verdict: "iterate",
      confidence: 0.47,
      review_reason: "Ensemble disagreement: 67% agreement across 3 models. Votes: pass, iterate, iterate",
      ensemble_votes: [
        "claude/claude-sonnet-4-6: pass (0.72)",
        "openai/gpt-4o-mini: iterate (0.70)",
        "google/gemini-flash-latest: iterate (0.70)",
      ],
      rationale:
        "Mixed signal — CTR 1.6% vs 2.5% target, CVR 2.8% vs 5% target, BUT 2 real paid conversions on $220 spend.",
    },
    {
      run_id: "demo-2b3c4d5e-6f78-9012-3456-7890abcdef12",
      idea_title: "FacturAI EC",
      verdict: "pass",
      confidence: 0.55,
      review_reason: "Ensemble disagreement: 67% agreement across 3 models. Votes: pass, pass, kill",
      ensemble_votes: [
        "claude/claude-sonnet-4-6: pass (0.85)",
        "openai/gpt-4o-mini: pass (0.78)",
        "google/gemini-flash-latest: kill (0.80)",
      ],
      rationale: "Gemini flagged CAC concerns despite the other two recommending PASS.",
    },
  ],
};

export default function RevisionPage() {
  const [data, setData] = useState<Pending>(DEMO);
  const [loading, setLoading] = useState(true);
  const [usingDemo, setUsingDemo] = useState(true);

  useEffect(() => {
    authFetch(`/api/v1/gate/pending-review`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((json: Pending) => {
        setData(json);
        setUsingDemo(false);
      })
      .catch(() => setUsingDemo(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          Revisión pendiente
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Fábricas donde el ensemble Claude + GPT + Gemini no alcanzó &ge; 67% de acuerdo.
          Tu veredicto se loggea para calibración futura.
        </p>
      </header>

      <div
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: "16px 20px",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 2 }}>
            {loading ? "Cargando..." : usingDemo ? "DEMO (API offline)" : "EN VIVO"}
          </div>
          <div style={{ color: "#fff", fontSize: 24, fontWeight: 700 }}>
            {data.pending_count} pendientes
          </div>
        </div>
        <div style={{ color: "#00D4FF", fontSize: 13 }}>
          API: {API}
        </div>
      </div>

      {data.items.length === 0 && !loading && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>
          No hay fábricas pendientes de revisión — todas las decisiones tienen consenso.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {data.items.map((item) => (
          <ReviewCard key={item.run_id} item={item} usingDemo={usingDemo} />
        ))}
      </div>
    </main>
  );
}

function ReviewCard({ item, usingDemo }: { item: PendingItem; usingDemo: boolean }) {
  const [open, setOpen] = useState(false);
  const [verdict, setVerdict] = useState<string>(item.verdict);
  const [reason, setReason] = useState("");
  const [decidedBy, setDecidedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const submit = async () => {
    if (reason.length < 10) {
      setResult("La razón debe tener al menos 10 caracteres.");
      return;
    }
    if (decidedBy.length < 2) {
      setResult("Indica tu nombre o email.");
      return;
    }
    setSubmitting(true);
    try {
      if (usingDemo) {
        // demo: just simulate success
        await new Promise((r) => setTimeout(r, 600));
        setResult(`✓ DEMO: verdict=${verdict} loggeado para ${item.idea_title}`);
      } else {
        const r = await authFetch(`/api/v1/gate/runs/${item.run_id}/human-override`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ verdict, reason, decided_by: decidedBy }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const json = await r.json();
        setResult(`✓ Verdict ${json.override_verdict} guardado por ${json.decided_by}`);
      }
    } catch (e) {
      setResult(`✗ Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: 20,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <h3 style={{ color: "#fff", fontSize: 18, fontWeight: 600, marginBottom: 4 }}>
            {item.idea_title}
          </h3>
          <div style={{ color: "#64748b", fontSize: 12, marginBottom: 10, fontFamily: "monospace" }}>
            {item.run_id}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 13, marginBottom: 12 }}>{item.rationale}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <VerdictBadge verdict={item.verdict.toUpperCase() as "PASS" | "KILL" | "ITERATE"} />
          <div style={{ color: "#FFB800", fontSize: 13, fontWeight: 600 }}>
            conf {(item.confidence * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <div
        style={{
          background: "#0B0F1A",
          border: "1px solid #1e293b",
          borderRadius: 8,
          padding: 12,
          marginTop: 8,
        }}
      >
        <div style={{ color: "#FFB800", fontSize: 11, marginBottom: 8, letterSpacing: 0.5 }}>
          MOTIVO DE ESCALACIÓN
        </div>
        <div style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 12 }}>{item.review_reason}</div>
        <div style={{ color: "#64748b", fontSize: 11, marginBottom: 6, letterSpacing: 0.5 }}>
          VOTOS DEL ENSEMBLE
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {item.ensemble_votes.map((v, i) => (
            <div key={i} style={{ color: "#94a3b8", fontSize: 13, fontFamily: "monospace" }}>
              • {v}
            </div>
          ))}
        </div>
      </div>

      {!open ? (
        <button
          onClick={() => setOpen(true)}
          style={{
            marginTop: 16,
            padding: "10px 20px",
            background: "#00D4FF",
            color: "#0B0F1A",
            border: "none",
            borderRadius: 8,
            fontWeight: 700,
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          Decidir manualmente →
        </button>
      ) : (
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
              Veredicto final
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              {(["pass", "iterate", "kill"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setVerdict(v)}
                  style={{
                    flex: 1,
                    padding: "10px 12px",
                    background: verdict === v ? "#00D4FF" : "#0B0F1A",
                    color: verdict === v ? "#0B0F1A" : "#94a3b8",
                    border: `1px solid ${verdict === v ? "#00D4FF" : "#1e293b"}`,
                    borderRadius: 6,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    textTransform: "uppercase",
                  }}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
              Razón (min 10 chars — se usa para calibración)
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              style={{
                width: "100%",
                padding: 10,
                background: "#0B0F1A",
                color: "#fff",
                border: "1px solid #1e293b",
                borderRadius: 6,
                fontSize: 13,
                fontFamily: "inherit",
                resize: "vertical",
              }}
              placeholder="Ej. CTR es bajo pero las 2 conversiones reales muestran intent claro de adopción..."
            />
          </div>
          <div>
            <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
              Tu nombre o email
            </label>
            <input
              value={decidedBy}
              onChange={(e) => setDecidedBy(e.target.value)}
              style={{
                width: "100%",
                padding: 10,
                background: "#0B0F1A",
                color: "#fff",
                border: "1px solid #1e293b",
                borderRadius: 6,
                fontSize: 13,
                fontFamily: "inherit",
              }}
              placeholder="cristian@circles-ai.ai"
            />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={submit}
              disabled={submitting}
              style={{
                padding: "10px 20px",
                background: "#00E5A0",
                color: "#0B0F1A",
                border: "none",
                borderRadius: 8,
                fontWeight: 700,
                fontSize: 14,
                cursor: submitting ? "wait" : "pointer",
                opacity: submitting ? 0.6 : 1,
              }}
            >
              {submitting ? "Guardando..." : "Guardar veredicto"}
            </button>
            <button
              onClick={() => setOpen(false)}
              style={{
                padding: "10px 20px",
                background: "transparent",
                color: "#94a3b8",
                border: "1px solid #1e293b",
                borderRadius: 8,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              Cancelar
            </button>
          </div>
          {result && (
            <div
              style={{
                color: result.startsWith("✓") ? "#00E5A0" : "#FF4444",
                fontSize: 13,
                paddingTop: 4,
              }}
            >
              {result}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
