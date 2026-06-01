"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M8.0 — Analytics ejecutivo.
 *
 * Visualiza time series + tops + feedback distribution sin librerías
 * externas. Bars CSS + SVG sparklines puros.
 */

type Bucket = { date: string; count: number };
type VerdictBucket = { date: string; pass_count: number; kill_count: number; iterate_count: number };
type CostBucket = { date: string; cost_usd: number };
type TopItem = { label: string; count: number };

type Analytics = {
  window_days: number;
  signals_per_day: Bucket[];
  runs_per_day: Bucket[];
  verdicts_per_day: VerdictBucket[];
  cost_per_day: CostBucket[];
  top_topics: TopItem[];
  top_sources: TopItem[];
  feedback_distribution: { up: number; down: number; unmarked: number };
  totals: {
    signals_in_window: number;
    runs_in_window: number;
    cost_total_usd: number;
    pass_rate_pct: number;
  };
};

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState(30);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authFetch(`/api/v1/analytics/timeseries?window_days=${windowDays}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, [windowDays]);

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1300, margin: "0 auto" }}>
      <header style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
            📈 Analytics
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            Vista ejecutiva: signals/runs/cost por día + tops + feedback distribution.
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
          <label style={{ color: "#94a3b8", fontSize: 12 }}>Ventana:</label>
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(parseInt(e.target.value, 10))}
            style={{ background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b", borderRadius: 6, padding: "4px 8px", fontSize: 12 }}
          >
            <option value={7}>7 días</option>
            <option value={30}>30 días</option>
            <option value={90}>90 días</option>
            <option value={180}>180 días</option>
          </select>
          <button
            onClick={refresh}
            style={{ padding: "6px 14px", background: "transparent", color: "#00D4FF", border: "1px solid #00D4FF", borderRadius: 6, fontSize: 13, cursor: "pointer" }}
          >
            ↻ Refresh
          </button>
        </div>
      </header>

      {error && (
        <div style={{ color: "#FF4444", padding: 12, marginBottom: 16, background: "rgba(255,68,68,0.06)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading && !data && (
        <div style={{ color: "#94a3b8", padding: 32, textAlign: "center" }}>Cargando…</div>
      )}

      {data && (
        <>
          {/* KPI cards */}
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
            <KPI label="Señales nuevas" value={data.totals.signals_in_window} accent="#00D4FF" />
            <KPI label="Runs ejecutados" value={data.totals.runs_in_window} accent="#A78BFA" />
            <KPI label="Pass rate" value={`${data.totals.pass_rate_pct}%`} accent="#00E5A0" />
            <KPI label="Costo total LLM" value={`$${data.totals.cost_total_usd.toFixed(4)}`} accent="#FFB800" />
          </section>

          {/* Time series: Signals + Runs */}
          <Section title="📡 Señales capturadas por día">
            <BarChart buckets={data.signals_per_day} color="#00D4FF" />
          </Section>

          <Section title="🏭 Runs ejecutados por día">
            <BarChart buckets={data.runs_per_day} color="#A78BFA" />
          </Section>

          {/* Stacked verdicts */}
          <Section title="🎯 Verdicts por día (PASS / ITERATE / KILL)">
            <StackedVerdictChart buckets={data.verdicts_per_day} />
          </Section>

          {/* Cost trend */}
          <Section title="💰 Costo LLM por día (USD)">
            <BarChart
              buckets={data.cost_per_day.map((b) => ({ date: b.date, count: b.cost_usd }))}
              color="#FFB800"
              format={(v) => `$${v.toFixed(3)}`}
            />
          </Section>

          {/* Two-column: top topics + top sources */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            <Section title="🏷️ Top topics (suggested_topic)">
              <TopList items={data.top_topics} accent="#00D4FF" />
            </Section>
            <Section title="📰 Top fuentes por señales">
              <TopList items={data.top_sources} accent="#A78BFA" />
            </Section>
          </div>

          {/* Feedback distribution */}
          <Section title="👍 Distribución de feedback">
            <FeedbackBar dist={data.feedback_distribution} />
          </Section>
        </>
      )}
    </main>
  );
}

function KPI({ label, value, accent }: { label: string; value: string | number; accent: string }) {
  return (
    <div style={{ padding: 14, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 8 }}>
      <div style={{ color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
      <div style={{ color: accent, fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 24, padding: 16, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12 }}>
      <h2 style={{ color: "#fff", fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 12 }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function BarChart({ buckets, color, format }: { buckets: { date: string; count: number }[]; color: string; format?: (v: number) => string }) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 100, paddingBottom: 16, position: "relative" }}>
      {buckets.map((b, i) => {
        const heightPct = (b.count / max) * 100;
        return (
          <div
            key={i}
            title={`${b.date}: ${format ? format(b.count) : b.count}`}
            style={{
              flex: 1,
              minWidth: 2,
              background: heightPct > 0 ? color : "#1e293b",
              height: `${Math.max(2, heightPct)}%`,
              borderRadius: "2px 2px 0 0",
              transition: "height 200ms ease",
              cursor: "default",
            }}
          />
        );
      })}
      <div style={{ position: "absolute", bottom: 0, left: 0, fontSize: 9, color: "#64748b", fontFamily: "monospace" }}>
        {buckets[0]?.date}
      </div>
      <div style={{ position: "absolute", bottom: 0, right: 0, fontSize: 9, color: "#64748b", fontFamily: "monospace" }}>
        {buckets[buckets.length - 1]?.date}
      </div>
    </div>
  );
}

function StackedVerdictChart({ buckets }: { buckets: { date: string; pass_count: number; kill_count: number; iterate_count: number }[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.pass_count + b.iterate_count + b.kill_count));
  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 100, paddingBottom: 16, position: "relative" }}>
        {buckets.map((b, i) => {
          const total = b.pass_count + b.iterate_count + b.kill_count;
          const totalPct = (total / max) * 100;
          if (total === 0) {
            return <div key={i} style={{ flex: 1, minWidth: 2, background: "#1e293b", height: 2 }} />;
          }
          return (
            <div
              key={i}
              title={`${b.date}: PASS ${b.pass_count} · ITERATE ${b.iterate_count} · KILL ${b.kill_count}`}
              style={{ flex: 1, minWidth: 2, display: "flex", flexDirection: "column-reverse", height: `${totalPct}%` }}
            >
              {b.pass_count > 0 && <div style={{ background: "#00E5A0", flex: b.pass_count }} />}
              {b.iterate_count > 0 && <div style={{ background: "#FFB800", flex: b.iterate_count }} />}
              {b.kill_count > 0 && <div style={{ background: "#FF4444", flex: b.kill_count }} />}
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11 }}>
        <span style={{ color: "#00E5A0" }}>● PASS</span>
        <span style={{ color: "#FFB800" }}>● ITERATE</span>
        <span style={{ color: "#FF4444" }}>● KILL</span>
      </div>
    </>
  );
}

function TopList({ items, accent }: { items: TopItem[]; accent: string }) {
  if (items.length === 0) {
    return <div style={{ color: "#64748b", fontSize: 12, fontStyle: "italic", padding: 12 }}>Sin data en esta ventana.</div>;
  }
  const max = Math.max(...items.map((i) => i.count));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.map((it, idx) => {
        const widthPct = (it.count / max) * 100;
        return (
          <div key={idx} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            <span style={{ color: "#94a3b8", width: 18, fontFamily: "monospace", fontSize: 10 }}>{idx + 1}.</span>
            <div style={{ flex: 1, height: 16, background: "#0B0F1A", borderRadius: 3, position: "relative", overflow: "hidden" }}>
              <div style={{ width: `${widthPct}%`, height: "100%", background: `${accent}30`, borderRight: `2px solid ${accent}` }} />
              <span style={{ position: "absolute", left: 6, top: 0, color: "#cbd5e1", fontSize: 11, lineHeight: "16px", textTransform: "capitalize" }}>
                {it.label}
              </span>
            </div>
            <span style={{ color: accent, fontFamily: "monospace", fontSize: 11, fontWeight: 700, minWidth: 24, textAlign: "right" }}>
              {it.count}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function FeedbackBar({ dist }: { dist: { up: number; down: number; unmarked: number } }) {
  const total = dist.up + dist.down + dist.unmarked;
  if (total === 0) {
    return <div style={{ color: "#64748b", fontSize: 12, fontStyle: "italic" }}>Sin señales aún.</div>;
  }
  return (
    <>
      <div style={{ display: "flex", height: 16, borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b" }}>
        {dist.up > 0 && <div style={{ flex: dist.up, background: "#00E5A0" }} title={`👍 ${dist.up}`} />}
        {dist.down > 0 && <div style={{ flex: dist.down, background: "#FF4444" }} title={`👎 ${dist.down}`} />}
        {dist.unmarked > 0 && <div style={{ flex: dist.unmarked, background: "#475569" }} title={`Sin marcar ${dist.unmarked}`} />}
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "#cbd5e1" }}>
        <span><strong style={{ color: "#00E5A0" }}>👍 {dist.up}</strong> ({((dist.up / total) * 100).toFixed(1)}%)</span>
        <span><strong style={{ color: "#FF4444" }}>👎 {dist.down}</strong> ({((dist.down / total) * 100).toFixed(1)}%)</span>
        <span><strong style={{ color: "#94a3b8" }}>Sin marcar {dist.unmarked}</strong> ({((dist.unmarked / total) * 100).toFixed(1)}%)</span>
      </div>
    </>
  );
}
