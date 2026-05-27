"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch } from "@/lib/auth";

type Signal = {
  id: number;
  source_id: number | null;
  source_kind: string;
  theme: string;
  score: number;
  excerpt: string;
  evidence_urls: string[];
  suggested_topic: string;
  feedback: string | null;
  promoted_run_id: string | null;
  trend_score: number;
  created_at: number;
};

export default function SenalesPage() {
  const router = useRouter();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0.5);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authFetch(`/api/v1/signals?limit=200&min_score=${minScore}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSignals((await r.json()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [minScore]);

  const setFeedback = async (id: number, fb: "up" | "down" | "clear") => {
    try {
      await authFetch(`/api/v1/signals/${id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: fb }),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const promote = async (id: number) => {
    if (!confirm("¿Promover esta señal a una corrida completa del workflow? Cuesta ~$0.06.")) return;
    try {
      const r = await authFetch("/api/v1/gate/run-from-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_id: id }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      alert(`✓ Run ${data.run_id} creado · verdict=${data.verdict}`);
      router.push(`/cazar?run_id=${data.run_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          📡 Señales capturadas
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          El cazador extrae estas señales de tus fuentes configuradas. Da 👍 a las
          relevantes, 👎 a las que no, y promueve las prometedoras a una corrida
          completa del workflow.
        </p>
      </header>

      {/* Filter + refresh */}
      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Score mínimo:</label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={minScore}
          onChange={(e) => setMinScore(parseFloat(e.target.value))}
          style={{ width: 200 }}
        />
        <span style={{ color: "#00D4FF", fontSize: 13, fontFamily: "monospace" }}>
          ≥ {minScore.toFixed(1)}
        </span>
        <button
          onClick={refresh}
          style={{
            marginLeft: "auto", padding: "6px 14px", background: "transparent",
            color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 13,
            cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </section>

      {error && <div style={{ color: "#FF4444", padding: 16, marginBottom: 16 }}>{error}</div>}

      {loading && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>Cargando…</div>
      )}

      {!loading && signals.length === 0 && (
        <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>
          No hay señales con score ≥ {minScore.toFixed(1)}. Ve a{" "}
          <a href="/cazar/fuentes" style={{ color: "#00D4FF" }}>Fuentes</a> y
          ejecuta un escaneo.
        </div>
      )}

      {/* Cards */}
      <div style={{ display: "grid", gap: 12 }}>
        {signals.map((s) => (
          <SignalCard
            key={s.id}
            signal={s}
            onFeedback={(fb) => setFeedback(s.id, fb)}
            onPromote={() => promote(s.id)}
          />
        ))}
      </div>
    </main>
  );
}

function SignalCard({
  signal,
  onFeedback,
  onPromote,
}: {
  signal: Signal;
  onFeedback: (fb: "up" | "down" | "clear") => void;
  onPromote: () => void;
}) {
  const scoreColor =
    signal.score >= 0.8 ? "#00E5A0" : signal.score >= 0.6 ? "#FFB800" : "#94a3b8";
  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{
              padding: "2px 8px", background: "rgba(0,212,255,0.1)",
              color: "#00D4FF", borderRadius: 4, fontSize: 10, fontFamily: "monospace", textTransform: "uppercase",
            }}>
              {signal.source_kind}
            </span>
            <span style={{ color: scoreColor, fontSize: 13, fontWeight: 700, fontFamily: "monospace" }}>
              score {signal.score.toFixed(2)}
            </span>
            {signal.trend_score >= 1 && (
              <span style={{
                padding: "2px 8px", background: "rgba(255,184,0,0.1)",
                color: "#FFB800", borderRadius: 4, fontSize: 11, fontFamily: "monospace", fontWeight: 700,
              }}
              title={`Tema reaparece ${signal.trend_score} ${signal.trend_score === 1 ? 'vez' : 'veces'} en últimos 7 días`}
              >
                🔥 trend +{signal.trend_score.toFixed(0)}
              </span>
            )}
            {signal.promoted_run_id && (
              <span style={{
                padding: "2px 8px", background: "rgba(0,229,160,0.1)",
                color: "#00E5A0", borderRadius: 4, fontSize: 10, textTransform: "uppercase",
              }}>
                ✓ Promovida
              </span>
            )}
          </div>
          <h3 style={{ color: "#fff", fontSize: 16, fontWeight: 600, marginBottom: 6 }}>{signal.theme}</h3>
          <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5, marginBottom: 8 }}>{signal.excerpt}</p>
          {signal.suggested_topic && (
            <div style={{
              marginTop: 8, padding: 10, background: "#0B0F1A",
              border: "1px solid #1e293b", borderRadius: 6, color: "#94a3b8", fontSize: 12,
            }}>
              <strong style={{ color: "#cbd5e1" }}>Topic sugerido:</strong> {signal.suggested_topic}
            </div>
          )}
          {signal.evidence_urls.length > 0 && (
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {signal.evidence_urls.map((u, i) => (
                <a
                  key={i}
                  href={u}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    color: "#00D4FF", fontSize: 11, padding: "2px 8px",
                    background: "rgba(0,212,255,0.05)", borderRadius: 4,
                    textDecoration: "none", fontFamily: "monospace",
                  }}
                >
                  {new URL(u).hostname}
                </a>
              ))}
            </div>
          )}
        </div>
        {/* Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 100 }}>
          <button
            onClick={() => onFeedback("up")}
            style={{
              padding: "6px 12px",
              background: signal.feedback === "up" ? "#00E5A0" : "transparent",
              color: signal.feedback === "up" ? "#0B0F1A" : "#00E5A0",
              border: "1px solid #00E5A0", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            👍 Up
          </button>
          <button
            onClick={() => onFeedback("down")}
            style={{
              padding: "6px 12px",
              background: signal.feedback === "down" ? "#FF4444" : "transparent",
              color: signal.feedback === "down" ? "#fff" : "#FF4444",
              border: "1px solid #FF4444", borderRadius: 6, fontSize: 12, cursor: "pointer",
            }}
          >
            👎 Down
          </button>
          {signal.feedback && (
            <button
              onClick={() => onFeedback("clear")}
              style={{
                padding: "4px 10px", background: "transparent", color: "#64748b",
                border: "1px solid #1e293b", borderRadius: 6, fontSize: 11, cursor: "pointer",
              }}
            >
              Limpiar
            </button>
          )}
          <button
            onClick={onPromote}
            disabled={!!signal.promoted_run_id}
            style={{
              marginTop: 4, padding: "8px 12px",
              background: signal.promoted_run_id ? "#1e293b" : "#00D4FF",
              color: signal.promoted_run_id ? "#64748b" : "#0B0F1A",
              border: "none", borderRadius: 6, fontSize: 12, fontWeight: 700,
              cursor: signal.promoted_run_id ? "not-allowed" : "pointer",
            }}
          >
            {signal.promoted_run_id ? "Ya promovida" : "→ Promover a idea"}
          </button>
        </div>
      </div>
    </div>
  );
}
