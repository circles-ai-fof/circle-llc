"use client";

import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

/**
 * M7.5 — Deploy diagnostic UI.
 *
 * Visualiza la respuesta de /api/v1/admin/diagnose-deploy: lista issues
 * categorizadas por severity con fix hints accionables.
 */

type Issue = {
  severity: "error" | "warning" | "info";
  category: string;
  message: string;
  fix_hint: string;
};

type Diagnosis = {
  overall_status: "ready" | "warnings" | "errors";
  error_count: number;
  warning_count: number;
  issues: Issue[];
  summary: string;
};

const SEVERITY_META: Record<string, { icon: string; color: string; label: string }> = {
  error:   { icon: "🚫", color: "#FF4444", label: "ERROR" },
  warning: { icon: "⚠️",  color: "#FFB800", label: "WARNING" },
  info:    { icon: "ℹ️",  color: "#00D4FF", label: "INFO" },
};

const STATUS_META: Record<string, { icon: string; color: string; label: string }> = {
  ready:    { icon: "✓",  color: "#00E5A0", label: "READY FOR PRODUCTION" },
  warnings: { icon: "⚠",  color: "#FFB800", label: "FUNCIONA CON DEGRADACIÓN" },
  errors:   { icon: "✗",  color: "#FF4444", label: "NO LISTO — CORREGIR ERRORES" },
};

export default function DiagnoseDeployPage() {
  const [data, setData] = useState<Diagnosis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authFetch("/api/v1/admin/diagnose-deploy");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  if (loading && !data) {
    return <main style={{ padding: 32, color: "#94a3b8", textAlign: "center" }}>Diagnosticando…</main>;
  }

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
            🩺 Deploy Diagnostic
          </h1>
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            Detecta misconfig común antes de despliegue: env vars, CORS, SMTP, cron.
          </p>
        </div>
        <button
          onClick={refresh}
          style={{
            marginLeft: "auto", padding: "6px 14px", background: "transparent",
            color: "#00D4FF", border: "1px solid #00D4FF",
            borderRadius: 6, fontSize: 13, cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </header>

      {error && (
        <div style={{ color: "#FF4444", padding: 12, marginBottom: 16, background: "rgba(255,68,68,0.06)", borderRadius: 8 }}>
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Overall status banner */}
          <section style={{
            padding: 16, marginBottom: 24,
            background: `${STATUS_META[data.overall_status].color}10`,
            border: `2px solid ${STATUS_META[data.overall_status].color}`,
            borderRadius: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <span style={{ fontSize: 28 }}>{STATUS_META[data.overall_status].icon}</span>
              <div>
                <div style={{ color: STATUS_META[data.overall_status].color, fontSize: 14, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                  {STATUS_META[data.overall_status].label}
                </div>
                <div style={{ color: "#cbd5e1", fontSize: 13 }}>{data.summary}</div>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 16, fontSize: 12, fontFamily: "monospace" }}>
                <span style={{ color: "#FF4444" }}>🚫 {data.error_count}</span>
                <span style={{ color: "#FFB800" }}>⚠️ {data.warning_count}</span>
                <span style={{ color: "#00D4FF" }}>ℹ️ {data.issues.length - data.error_count - data.warning_count}</span>
              </div>
            </div>
          </section>

          {/* Issues por categoría */}
          {data.issues.length === 0 ? (
            <div style={{
              padding: 32, textAlign: "center",
              background: "#0F1525", border: "1px solid #1e293b", borderRadius: 12,
              color: "#00E5A0", fontSize: 16,
            }}>
              ✓ Cero issues detectados. Sistema completamente configurado.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {data.issues.map((issue, idx) => {
                const meta = SEVERITY_META[issue.severity];
                return (
                  <div key={idx} style={{
                    padding: 14, background: "#0F1525",
                    border: `1px solid ${meta.color}40`,
                    borderLeft: `3px solid ${meta.color}`,
                    borderRadius: 8,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                      <span style={{ fontSize: 16 }}>{meta.icon}</span>
                      <span style={{ color: meta.color, fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>
                        {meta.label}
                      </span>
                      <span style={{ marginLeft: 4, padding: "1px 8px", background: "#0B0F1A", color: "#94a3b8", borderRadius: 3, fontSize: 10, fontFamily: "monospace", textTransform: "uppercase" }}>
                        {issue.category}
                      </span>
                    </div>
                    <div style={{ color: "#fff", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                      {issue.message}
                    </div>
                    <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.5, paddingTop: 6, borderTop: "1px solid #1e293b" }}>
                      💡 <strong>Fix:</strong> {issue.fix_hint}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div style={{ marginTop: 24, padding: 12, background: "#0F1525", border: "1px solid #1e293b", borderRadius: 8, color: "#64748b", fontSize: 11 }}>
            💡 Cómo usar: corré este check antes de cada deploy. Si overall_status=ready, el sistema está listo.
            Si hay errors, esos son bloqueantes (ALLOWED_EMAILS vacío rompe el login). Warnings son degradación
            funcional. Info son notas para optimización futura.
          </div>
        </>
      )}
    </main>
  );
}
