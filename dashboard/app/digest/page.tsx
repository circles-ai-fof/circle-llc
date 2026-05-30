"use client";

import { useEffect, useState } from "react";
import { authFetch, getSession } from "@/lib/auth";

/**
 * M6.1 — Weekly Digest viewer.
 *
 * Muestra el digest semanal en un iframe que apunta a /api/v1/digest/preview
 * (HTML autocontenido). El founder puede:
 *  - Cambiar window_days (7, 14, 30)
 *  - Copiar el HTML al portapapeles (para pegarlo en Mailgun/SendGrid)
 *  - Descargar como .html
 *  - Ver versión texto plano (para WhatsApp/Telegram)
 *
 * Sin SMTP integrado — el envío real queda a M6.2 cuando configures un
 * provider transaccional.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

export default function DigestPage() {
  const [windowDays, setWindowDays] = useState(7);
  const [textVersion, setTextVersion] = useState<string | null>(null);
  const [copiedHtml, setCopiedHtml] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{ sent: boolean; detail: string; smtp_configured: boolean; recipients_count: number } | null>(null);

  // Construir URL con token Bearer en query (HTMLResponse no soporta auth header
  // dentro del iframe normalmente; usamos sessionToken para auth via API)
  const [previewSrc, setPreviewSrc] = useState<string>("");

  useEffect(() => {
    const session = getSession();
    if (!session) {
      setError("No hay sesión activa. Loguéate primero.");
      return;
    }
    // El backend acepta Bearer en header — pero un iframe directo no puede
    // setear headers. Workaround: fetch el HTML y meterlo en srcDoc.
    (async () => {
      try {
        const r = await authFetch(`/api/v1/digest/preview?window_days=${windowDays}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const html = await r.text();
        setPreviewSrc(html);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [windowDays]);

  const copyHtml = async () => {
    try {
      if (!previewSrc) return;
      await navigator.clipboard.writeText(previewSrc);
      setCopiedHtml(true);
      setTimeout(() => setCopiedHtml(false), 2000);
    } catch {
      alert("No se pudo copiar al portapapeles.");
    }
  };

  const downloadHtml = () => {
    if (!previewSrc) return;
    const blob = new Blob([previewSrc], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `digest_${new Date().toISOString().slice(0, 10)}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const fetchText = async () => {
    try {
      const r = await authFetch(`/api/v1/digest/text?window_days=${windowDays}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setTextVersion(await r.text());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const sendNow = async () => {
    if (sending) return;
    if (!confirm("¿Enviar el digest ahora a los destinatarios configurados en DIGEST_TO? Si SMTP_* no está configurado, el envío fallará suavemente.")) return;
    setSending(true);
    setSendResult(null);
    try {
      const r = await authFetch(`/api/v1/digest/send?window_days=${windowDays}`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSendResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <main style={{ padding: "clamp(20px, 4vw, 32px) clamp(16px, 4vw, 40px)", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#fff", marginBottom: 6 }}>
          📨 Weekly Digest
        </h1>
        <p style={{ color: "#94a3b8", fontSize: 13, maxWidth: 720 }}>
          Resumen semanal automático: stats + top oportunidades + nichos + eventos + trending.
          Sin LLM (costo $0). Copiá el HTML para pegarlo en tu cliente de email,
          o descargalo. El envío automático llega en M6.2.
        </p>
      </header>

      <section style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <label style={{ color: "#94a3b8", fontSize: 12 }}>Ventana:</label>
        <select
          value={windowDays}
          onChange={(e) => setWindowDays(parseInt(e.target.value, 10))}
          style={{
            background: "#0F1525", color: "#cbd5e1", border: "1px solid #1e293b",
            borderRadius: 6, padding: "4px 8px", fontSize: 12,
          }}
        >
          <option value={7}>Últimos 7 días</option>
          <option value={14}>Últimos 14 días</option>
          <option value={30}>Últimos 30 días</option>
        </select>
        <button
          onClick={copyHtml}
          disabled={!previewSrc}
          style={{
            padding: "6px 14px", background: "transparent",
            color: copiedHtml ? "#00E5A0" : "#00D4FF",
            border: `1px solid ${copiedHtml ? "#00E5A0" : "#00D4FF"}`,
            borderRadius: 6, fontSize: 13, cursor: previewSrc ? "pointer" : "not-allowed",
          }}
        >
          {copiedHtml ? "✓ Copiado" : "📋 Copiar HTML"}
        </button>
        <button
          onClick={downloadHtml}
          disabled={!previewSrc}
          style={{
            padding: "6px 14px", background: "transparent",
            color: "#A78BFA", border: "1px solid #A78BFA",
            borderRadius: 6, fontSize: 13, cursor: previewSrc ? "pointer" : "not-allowed",
          }}
        >
          💾 Descargar .html
        </button>
        <button
          onClick={fetchText}
          style={{
            padding: "6px 14px", background: "transparent",
            color: "#94a3b8", border: "1px solid #1e293b",
            borderRadius: 6, fontSize: 13, cursor: "pointer",
          }}
        >
          📝 Ver versión texto plano
        </button>
        <button
          onClick={sendNow}
          disabled={sending}
          title="POST /api/v1/digest/send. Si SMTP_* no está configurado en el backend, retorna sin enviar (no es error)."
          style={{
            padding: "6px 14px", background: "transparent",
            color: sending ? "#64748b" : "#00E5A0",
            border: `1px solid ${sending ? "#1e293b" : "#00E5A0"}`,
            borderRadius: 6, fontSize: 13, fontWeight: 600,
            cursor: sending ? "wait" : "pointer",
          }}
        >
          {sending ? "Enviando…" : "📨 Enviar ahora"}
        </button>
        <span style={{ marginLeft: "auto", color: "#64748b", fontSize: 11 }}>
          {API}/api/v1/digest/preview
        </span>
      </section>

      {sendResult && (
        <div style={{
          marginBottom: 16, padding: 12,
          background: sendResult.sent ? "rgba(0,229,160,0.06)" : "rgba(255,184,0,0.06)",
          border: `1px solid ${sendResult.sent ? "rgba(0,229,160,0.4)" : "rgba(255,184,0,0.4)"}`,
          borderRadius: 8, fontSize: 13, color: "#cbd5e1",
        }}>
          {sendResult.sent ? (
            <>✓ <strong style={{ color: "#00E5A0" }}>Enviado</strong> a {sendResult.recipients_count} destinatario{sendResult.recipients_count === 1 ? "" : "s"}. {sendResult.detail}</>
          ) : !sendResult.smtp_configured ? (
            <>⚠️ <strong style={{ color: "#FFB800" }}>SMTP no configurado.</strong> Setea <code style={{ background: "#0B0F1A", padding: "1px 4px", borderRadius: 3 }}>SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DIGEST_FROM, DIGEST_TO</code> en las env vars del backend (Railway/Render) y reintenta.</>
          ) : (
            <>✗ <strong style={{ color: "#FF4444" }}>Fallo:</strong> {sendResult.detail}</>
          )}
        </div>
      )}

      {error && (
        <div style={{
          padding: 12, marginBottom: 16, color: "#FF4444",
          background: "rgba(255,68,68,0.06)", border: "1px solid rgba(255,68,68,0.3)",
          borderRadius: 8, fontSize: 13,
        }}>
          ⚠ {error}
        </div>
      )}

      {previewSrc && (
        <div style={{
          border: "1px solid #1e293b", borderRadius: 12, overflow: "hidden",
          background: "#0B0F1A",
        }}>
          <iframe
            srcDoc={previewSrc}
            title="Weekly Digest Preview"
            style={{
              width: "100%", height: "1400px", border: "none",
              background: "#0B0F1A",
            }}
          />
        </div>
      )}

      {textVersion && (
        <section style={{ marginTop: 24 }}>
          <h2 style={{ color: "#94a3b8", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
            Versión texto plano (para WhatsApp/Telegram)
          </h2>
          <pre style={{
            background: "#0F1525", border: "1px solid #1e293b", borderRadius: 8,
            padding: 16, color: "#cbd5e1", fontSize: 12, lineHeight: 1.5,
            overflowX: "auto", fontFamily: "Menlo, Monaco, 'Courier New', monospace",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {textVersion}
          </pre>
        </section>
      )}
    </main>
  );
}
