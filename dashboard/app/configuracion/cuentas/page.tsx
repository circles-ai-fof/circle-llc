"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

type Account = {
  platform: string;
  status: string;
  needs_credentials: boolean;
  missing_keys: string[];
  configured_keys: string[];
  oauth_required: boolean;
  message: string;
  recommended_kind: string | null;
  notes: string;
  user_notes: string | null;
  configured_at: number | null;
};

const STATUS_LABELS: Record<string, { color: string; bg: string; label: string }> = {
  ready: { color: "#00E5A0", bg: "rgba(0,229,160,0.1)", label: "✅ Lista" },
  configured: { color: "#00E5A0", bg: "rgba(0,229,160,0.1)", label: "✅ Configurada" },
  optional_credentials: { color: "#FFB800", bg: "rgba(255,184,0,0.1)", label: "⚠️ Opcional" },
  requires_credentials: { color: "#FFB800", bg: "rgba(255,184,0,0.1)", label: "⚠️ Faltan credenciales" },
  deferred: { color: "#FF4444", bg: "rgba(255,68,68,0.1)", label: "⛔ Diferida (ADR-011)" },
};

export default function CuentasPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingFor, setSavingFor] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await authFetch("/api/v1/connected-accounts");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setAccounts((await r.json()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const markAs = async (platform: string, status: string, notes?: string) => {
    setSavingFor(platform);
    try {
      const r = await authFetch("/api/v1/connected-accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, status, notes: notes || null }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingFor(null);
    }
  };

  // Group by status for cleaner sections
  const byStatus = {
    ready_and_configured: accounts.filter((a) =>
      ["ready", "configured"].includes(a.status)
    ),
    optional: accounts.filter((a) => a.status === "optional_credentials"),
    requires: accounts.filter((a) => a.status === "requires_credentials"),
    deferred: accounts.filter((a) => a.status === "deferred"),
  };

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          🔌 Cuentas conectadas
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 14, lineHeight: 1.5 }}>
          Estado de cada plataforma que el cazador puede monitorear. Las credenciales
          viven en <code style={{ background: "#0B0F1A", padding: "1px 6px", borderRadius: 3 }}>orchestrator/.env</code>;
          esta pantalla solo refleja qué está configurado y qué falta.
        </p>
      </header>

      {error && (
        <div style={{ color: "#FF4444", padding: 12, marginBottom: 16, background: "rgba(255,68,68,0.06)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {loading && <div style={{ color: "#94a3b8", padding: 40, textAlign: "center" }}>Cargando…</div>}

      {!loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <Section
            title="✅ Listas para monitorear"
            subtitle="Sin requisitos adicionales — el cazador ya las usa."
            accounts={byStatus.ready_and_configured}
            savingFor={savingFor}
            onMark={markAs}
          />
          <Section
            title="⚠️ Opcional: mejora con credenciales"
            subtitle="Funcionan sin configurar; con keys activan features adicionales."
            accounts={byStatus.optional}
            savingFor={savingFor}
            onMark={markAs}
          />
          {byStatus.requires.length > 0 && (
            <Section
              title="⚠️ Requieren credenciales"
              subtitle="No funcionan sin las API keys listadas."
              accounts={byStatus.requires}
              savingFor={savingFor}
              onMark={markAs}
            />
          )}
          <Section
            title="⛔ Diferidas por ADR-011"
            subtitle="Por costo, ToS o falta de OAuth viable. NO recomendamos activarlas aún."
            accounts={byStatus.deferred}
            savingFor={savingFor}
            onMark={markAs}
          />
        </div>
      )}
    </main>
  );
}

function Section({
  title,
  subtitle,
  accounts,
  savingFor,
  onMark,
}: {
  title: string;
  subtitle: string;
  accounts: Account[];
  savingFor: string | null;
  onMark: (p: string, s: string, notes?: string) => void;
}) {
  if (accounts.length === 0) return null;
  return (
    <section>
      <h2 style={{ color: "#fff", fontSize: 18, fontWeight: 600, marginBottom: 4 }}>{title}</h2>
      <p style={{ color: "#94a3b8", fontSize: 12, marginBottom: 12 }}>{subtitle}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
        {accounts.map((a) => (
          <PlatformCard key={a.platform} account={a} savingFor={savingFor} onMark={onMark} />
        ))}
      </div>
    </section>
  );
}

function PlatformCard({
  account: a,
  savingFor,
  onMark,
}: {
  account: Account;
  savingFor: string | null;
  onMark: (p: string, s: string, notes?: string) => void;
}) {
  const meta = STATUS_LABELS[a.status] || { color: "#94a3b8", bg: "#1e293b", label: a.status };
  return (
    <div
      style={{
        background: "#0F1525",
        border: "1px solid #1e293b",
        borderRadius: 10,
        padding: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ color: "#fff", fontSize: 15, fontWeight: 600, textTransform: "capitalize" }}>
          {a.platform}
        </span>
        <span
          style={{
            padding: "2px 8px",
            background: meta.bg,
            color: meta.color,
            borderRadius: 4,
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.4,
          }}
        >
          {meta.label}
        </span>
      </div>
      <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.55, marginBottom: 10 }}>
        {a.message}
      </div>
      {a.missing_keys.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: "#94a3b8", fontSize: 10, marginBottom: 4, fontWeight: 600, textTransform: "uppercase" }}>
            Variables faltantes en .env
          </div>
          <div>
            {a.missing_keys.map((k) => (
              <code
                key={k}
                style={{
                  background: "#0B0F1A",
                  padding: "2px 6px",
                  borderRadius: 3,
                  marginRight: 4,
                  fontSize: 11,
                  color: "#FFB800",
                  display: "inline-block",
                  marginBottom: 4,
                }}
              >
                {k}
              </code>
            ))}
          </div>
        </div>
      )}
      {a.configured_keys.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: "#94a3b8", fontSize: 10, marginBottom: 4, fontWeight: 600, textTransform: "uppercase" }}>
            Variables ya configuradas
          </div>
          <div>
            {a.configured_keys.map((k) => (
              <code
                key={k}
                style={{
                  background: "rgba(0,229,160,0.08)",
                  padding: "2px 6px",
                  borderRadius: 3,
                  marginRight: 4,
                  fontSize: 11,
                  color: "#00E5A0",
                  display: "inline-block",
                }}
              >
                {k}
              </code>
            ))}
          </div>
        </div>
      )}
      {a.user_notes && (
        <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 8, fontStyle: "italic" }}>
          📝 {a.user_notes}
        </div>
      )}
      {a.configured_at && (
        <div style={{ color: "#64748b", fontSize: 10, marginBottom: 8 }}>
          Marcada como configurada: {new Date(a.configured_at * 1000).toLocaleString("es-EC")}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {a.status !== "deferred" && (
          <button
            onClick={() => onMark(a.platform, "configured", "Marcado manualmente como configurado")}
            disabled={savingFor === a.platform}
            style={{
              padding: "4px 10px",
              background: "transparent",
              color: "#00E5A0",
              border: "1px solid #00E5A0",
              borderRadius: 4,
              fontSize: 11,
              cursor: "pointer",
            }}
          >
            ✓ Marcar como configurada
          </button>
        )}
      </div>
    </div>
  );
}
