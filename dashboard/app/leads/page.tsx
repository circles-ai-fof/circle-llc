"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type LeadItem = {
  slug: string;
  email: string;
  name: string | null;
  ts: number;
  ip_masked: string | null;
};

type LeadsList = { slug: string; count: number; leads: LeadItem[]; masked: boolean };
type StatsItem = { slug: string; count: number };
type Stats = { total_leads: number; by_slug: StatsItem[] };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LeadsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string>("techpulse-latam");
  const [list, setList] = useState<LeadsList | null>(null);
  const [loading, setLoading] = useState(true);
  const [secret, setSecret] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  const refreshStats = async () => {
    try {
      const r = await authFetch(`/api/v1/leads/stats`);
      if (!r.ok) throw new Error(`stats ${r.status}`);
      setStats(await r.json());
    } catch (e) {
      setErr(`Stats: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const refreshList = async (slug: string) => {
    try {
      const headers: HeadersInit = {};
      if (secret) headers["X-Gate-Secret"] = secret;
      const r = await authFetch(`/api/v1/leads/${slug}?limit=100`, { headers });
      if (!r.ok) throw new Error(`list ${r.status}`);
      setList(await r.json());
    } catch (e) {
      setErr(`List: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([refreshStats(), refreshList(selectedSlug)]).finally(() => setLoading(false));
  }, [selectedSlug, secret]);

  return (
    <main style={{ padding: "32px 40px", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          Leads
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14 }}>
          Emails capturados por cada fábrica activa. Por defecto enmascarados —
          ingresa el <code style={{ color: "#00D4FF" }}>GATE_RUN_SECRET</code>{" "}
          para ver completos.
        </p>
      </header>

      {/* Stats */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
          marginBottom: 24,
        }}
      >
        <StatCard
          label="Total leads"
          value={stats?.total_leads ?? 0}
          accent="#00D4FF"
          big
        />
        {(stats?.by_slug ?? []).map((s) => (
          <StatCard
            key={s.slug}
            label={s.slug}
            value={s.count}
            accent={s.slug === selectedSlug ? "#00E5A0" : "#94a3b8"}
            onClick={() => setSelectedSlug(s.slug)}
          />
        ))}
      </section>

      {/* Admin secret input */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          padding: 16,
          marginBottom: 20,
        }}
      >
        <label style={{ color: "#94a3b8", fontSize: 12, display: "block", marginBottom: 6 }}>
          X-Gate-Secret (opcional, para ver emails completos)
        </label>
        <input
          type="password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="Pega aquí el GATE_RUN_SECRET de Railway"
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
        {list && (
          <div style={{ marginTop: 8, color: list.masked ? "#FFB800" : "#00E5A0", fontSize: 12 }}>
            {list.masked ? "🔒 Emails enmascarados" : "✓ Vista admin (emails completos)"}
          </div>
        )}
      </section>

      {/* List */}
      <section
        style={{
          background: "#0F1525",
          border: "1px solid #1e293b",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #1e293b",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h2 style={{ color: "#fff", fontSize: 16, fontWeight: 600 }}>
            {selectedSlug} — {list?.count ?? 0} leads
          </h2>
          <button
            onClick={() => {
              setLoading(true);
              Promise.all([refreshStats(), refreshList(selectedSlug)]).finally(() => setLoading(false));
            }}
            style={{
              padding: "6px 12px",
              background: "transparent",
              color: "#00D4FF",
              border: "1px solid #00D4FF",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {loading ? "Cargando…" : "↻ Refresh"}
          </button>
        </div>

        {err && (
          <div style={{ padding: 16, color: "#FF4444", fontSize: 13 }}>
            ✗ {err} — API: {API}
          </div>
        )}

        {(!list || list.leads.length === 0) && !loading && !err && (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>
            Aún no hay leads capturados en <strong>{selectedSlug}</strong>.
          </div>
        )}

        {list && list.leads.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <Th>Email</Th>
                <Th>Nombre</Th>
                <Th>IP</Th>
                <Th>Fecha</Th>
              </tr>
            </thead>
            <tbody>
              {list.leads.map((l, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #1e293b" }}>
                  <Td mono>{l.email}</Td>
                  <Td>{l.name ?? "—"}</Td>
                  <Td mono>{l.ip_masked ?? "—"}</Td>
                  <Td>{new Date(l.ts * 1000).toLocaleString()}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

function StatCard({
  label,
  value,
  accent,
  big,
  onClick,
}: {
  label: string;
  value: number;
  accent: string;
  big?: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 12,
        padding: "16px 20px",
        cursor: onClick ? "pointer" : "default",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        if (onClick) (e.currentTarget as HTMLDivElement).style.borderColor = accent;
      }}
      onMouseLeave={(e) => {
        if (onClick) (e.currentTarget as HTMLDivElement).style.borderColor = "#1e293b";
      }}
    >
      <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 6, letterSpacing: 0.5, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ color: accent, fontSize: big ? 32 : 24, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: "left",
        padding: "12px 20px",
        color: "#94a3b8",
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: 0.5,
        textTransform: "uppercase",
      }}
    >
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td
      style={{
        padding: "12px 20px",
        color: "#cbd5e1",
        fontSize: 13,
        fontFamily: mono ? "monospace" : "inherit",
      }}
    >
      {children}
    </td>
  );
}
