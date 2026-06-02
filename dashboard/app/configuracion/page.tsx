"use client";

/**
 * Configuración — settings real conectadas a /api/v1/settings (M9.1).
 *
 * Permite al founder configurar:
 *   - i18n: locale, timezone, formato fecha/hora, moneda
 *   - auto_translate_to: idioma destino para traducir señales al scrapear
 *   - preferred_topics + excluded_topics: filtros de ideas
 *   - autonomy: max sources auto-discovered por semana
 *
 * Extra: botón "Traducir señales pendientes" llama bulk-translate
 * para backfillear señales que fueron capturadas antes de M9.1.
 */
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

type Settings = {
  locale: string;
  timezone: string;
  date_format: string;
  time_format: "12h" | "24h";
  currency: string;
  number_format: "es" | "en";
  auto_translate_to: string;
  preferred_regions: string[];
  preferred_topics: string[];
  excluded_topics: string[];
  auto_discovery_enabled: boolean;
  max_new_sources_per_week: number;
  updated_at: number;
};

const LOCALES = [
  { code: "es-EC", label: "Español (Ecuador)" },
  { code: "es-PE", label: "Español (Perú)" },
  { code: "es-CO", label: "Español (Colombia)" },
  { code: "es-MX", label: "Español (México)" },
  { code: "es-AR", label: "Español (Argentina)" },
  { code: "en-US", label: "English (US)" },
];

const TIMEZONES = [
  { code: "America/Lima", label: "Lima / Quito (UTC-5)" },
  { code: "America/Guayaquil", label: "Guayaquil (UTC-5)" },
  { code: "America/Bogota", label: "Bogotá (UTC-5)" },
  { code: "America/Mexico_City", label: "Ciudad de México (UTC-6)" },
  { code: "America/Argentina/Buenos_Aires", label: "Buenos Aires (UTC-3)" },
  { code: "America/Santiago", label: "Santiago (UTC-3/-4)" },
  { code: "America/New_York", label: "New York (UTC-5/-4)" },
  { code: "Europe/Madrid", label: "Madrid (UTC+1/+2)" },
  { code: "UTC", label: "UTC (sin zona)" },
];

const TRANSLATE_TARGETS = [
  { code: "", label: "— Desactivado (no traducir) —" },
  { code: "es", label: "Español neutro (LATAM)" },
  { code: "es-EC", label: "Español de Ecuador" },
  { code: "es-MX", label: "Español de México" },
  { code: "en", label: "English" },
  { code: "pt", label: "Português" },
];

const CURRENCIES = ["USD", "EUR", "PEN", "COP", "MXN", "ARS", "CLP", "BRL"];

const SECTION_STYLE = "rounded-xl border overflow-hidden";
const SECTION_HEADER = "px-4 py-3 border-b";
const FIELD_ROW = "px-4 py-3 flex items-center justify-between gap-4";
const INPUT_BASE =
  "px-3 py-1.5 rounded-md border text-sm bg-[#0B0F1A] border-[#1E2A3A] text-cyan-300 focus:outline-none focus:border-cyan-500";

export default function ConfiguracionPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bulkTranslating, setBulkTranslating] = useState(false);
  const [bulkResult, setBulkResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // local input string for the comma-separated topics
  const [preferredTopicsRaw, setPreferredTopicsRaw] = useState("");
  const [excludedTopicsRaw, setExcludedTopicsRaw] = useState("");

  // ------------------------------------------------------------------
  // Load on mount
  useEffect(() => {
    const s = getSession();
    if (!s) {
      setError("No estás logueado. Volvé a /login.");
      setLoading(false);
      return;
    }
    fetch(`${API}/api/v1/settings`, {
      headers: { Authorization: `Bearer ${s.token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: Settings) => {
        setSettings(data);
        setPreferredTopicsRaw((data.preferred_topics ?? []).join(", "));
        setExcludedTopicsRaw((data.excluded_topics ?? []).join(", "));
        setLoading(false);
      })
      .catch((e) => {
        setError(`Error cargando configuración: ${e.message}`);
        setLoading(false);
      });
  }, []);

  // ------------------------------------------------------------------
  // Save
  async function save<K extends keyof Settings>(patch: Partial<Settings>) {
    const s = getSession();
    if (!s || !settings) return;
    setSaving(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/v1/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${s.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(patch),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      const updated = (await r.json()) as Settings;
      setSettings(updated);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Error guardando: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  function commitTopics(field: "preferred_topics" | "excluded_topics", raw: string) {
    const list = raw
      .split(/[,\n]/)
      .map((t) => t.trim())
      .filter(Boolean);
    void save({ [field]: list } as Partial<Settings>);
  }

  // ------------------------------------------------------------------
  // Bulk translate
  async function runBulkTranslate() {
    const s = getSession();
    if (!s) return;
    setBulkTranslating(true);
    setBulkResult(null);
    try {
      const r = await fetch(`${API}/api/v1/signals/translate-bulk`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${s.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ limit: 50 }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(JSON.stringify(data));
      const t = data.translated ?? 0;
      const sk = data.skipped ?? 0;
      const f = data.failed ?? 0;
      const reason = data.reason ? ` — ${data.reason}` : "";
      setBulkResult(`✅ Traducidas: ${t} · Saltadas: ${sk} · Fallidas: ${f}${reason}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setBulkResult(`❌ Error: ${msg}`);
    } finally {
      setBulkTranslating(false);
    }
  }

  // ------------------------------------------------------------------
  // Render

  if (loading) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-sm text-gray-500 mt-2">Cargando…</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-sm text-red-400 mt-2">{error ?? "Sin datos"}</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          i18n, traducción automática, filtros de ideas y autonomía del cazador.
        </p>
        {saving && (
          <p className="text-xs text-cyan-400 mt-1">Guardando…</p>
        )}
        {error && (
          <p className="text-xs text-red-400 mt-1">{error}</p>
        )}
      </div>

      {/* --- Idioma & Región --- */}
      <div className={SECTION_STYLE} style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
        <div className={SECTION_HEADER} style={{ borderColor: "#1E2A3A" }}>
          <h2 className="text-sm font-semibold text-gray-300">Idioma & Región</h2>
          <p className="text-xs text-gray-500 mt-0.5">Cómo se muestra el contenido y las fechas.</p>
        </div>
        <div className="divide-y divide-[#1E2A3A]">
          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Idioma del dashboard (locale)</p>
              <p className="text-xs text-gray-600 mt-0.5">Afecta formatos de fecha y moneda.</p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.locale}
              onChange={(e) => save({ locale: e.target.value })}
            >
              {LOCALES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Zona horaria</p>
              <p className="text-xs text-gray-600 mt-0.5">
                Cómo se muestran los timestamps. Hoy: <span className="font-mono">{settings.timezone}</span>
              </p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.timezone}
              onChange={(e) => save({ timezone: e.target.value })}
            >
              {TIMEZONES.map((t) => (
                <option key={t.code} value={t.code}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Formato de fecha</p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.date_format}
              onChange={(e) => save({ date_format: e.target.value })}
            >
              <option value="DD/MM/YYYY">DD/MM/YYYY (es)</option>
              <option value="MM/DD/YYYY">MM/DD/YYYY (en-US)</option>
              <option value="YYYY-MM-DD">YYYY-MM-DD (ISO)</option>
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Formato de hora</p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.time_format}
              onChange={(e) => save({ time_format: e.target.value as "12h" | "24h" })}
            >
              <option value="24h">24h (14:30)</option>
              <option value="12h">12h (2:30 PM)</option>
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Moneda</p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.currency}
              onChange={(e) => save({ currency: e.target.value })}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Formato numérico</p>
              <p className="text-xs text-gray-600 mt-0.5">es: 1.000,50 · en: 1,000.50</p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.number_format}
              onChange={(e) => save({ number_format: e.target.value as "es" | "en" })}
            >
              <option value="es">es</option>
              <option value="en">en</option>
            </select>
          </div>
        </div>
      </div>

      {/* --- Traducción automática --- */}
      <div className={SECTION_STYLE} style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
        <div className={SECTION_HEADER} style={{ borderColor: "#1E2A3A" }}>
          <h2 className="text-sm font-semibold text-gray-300">Traducción automática (M9.1)</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Cuando el cazador escrapea, si la señal NO está en este idioma se traduce con Claude Haiku.
          </p>
        </div>
        <div className="divide-y divide-[#1E2A3A]">
          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Idioma destino</p>
              <p className="text-xs text-gray-600 mt-0.5">
                Vacío = desactivado · ~$0.001 por señal nueva.
              </p>
            </div>
            <select
              className={INPUT_BASE}
              value={settings.auto_translate_to}
              onChange={(e) => save({ auto_translate_to: e.target.value })}
            >
              {TRANSLATE_TARGETS.map((t) => (
                <option key={t.code} value={t.code}>{t.label}</option>
              ))}
            </select>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Traducir señales pendientes (backfill)</p>
              <p className="text-xs text-gray-600 mt-0.5">
                Las señales capturadas ANTES de activar la traducción quedan en inglés.
                Este botón las traduce hasta 50 por click (~$0.05 total).
              </p>
              {bulkResult && <p className="text-xs text-cyan-400 mt-1">{bulkResult}</p>}
            </div>
            <button
              className="px-3 py-1.5 rounded-md text-sm border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10 disabled:opacity-40"
              disabled={bulkTranslating || !settings.auto_translate_to}
              onClick={runBulkTranslate}
            >
              {bulkTranslating ? "Traduciendo…" : "Ejecutar"}
            </button>
          </div>
        </div>
      </div>

      {/* --- Filtros de ideas --- */}
      <div className={SECTION_STYLE} style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
        <div className={SECTION_HEADER} style={{ borderColor: "#1E2A3A" }}>
          <h2 className="text-sm font-semibold text-gray-300">Filtros de ideas</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Influye en ranking + sugerencias del SourceDiscoveryAgent.
          </p>
        </div>
        <div className="divide-y divide-[#1E2A3A]">
          <div className={FIELD_ROW + " flex-col items-stretch"}>
            <p className="text-sm text-gray-200 mb-1">Temas preferidos (separados por coma)</p>
            <textarea
              className={INPUT_BASE + " w-full font-mono"}
              rows={2}
              value={preferredTopicsRaw}
              onChange={(e) => setPreferredTopicsRaw(e.target.value)}
              onBlur={() => commitTopics("preferred_topics", preferredTopicsRaw)}
              placeholder="fintech, agtech, ai-builder, saas"
            />
          </div>
          <div className={FIELD_ROW + " flex-col items-stretch"}>
            <p className="text-sm text-gray-200 mb-1">Temas excluidos (separados por coma)</p>
            <textarea
              className={INPUT_BASE + " w-full font-mono"}
              rows={2}
              value={excludedTopicsRaw}
              onChange={(e) => setExcludedTopicsRaw(e.target.value)}
              onBlur={() => commitTopics("excluded_topics", excludedTopicsRaw)}
              placeholder="nft, metaverse, crypto"
            />
          </div>
          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Regiones preferidas</p>
              <p className="text-xs text-gray-600 mt-0.5 font-mono">
                {(settings.preferred_regions ?? []).join(", ") || "—"}
              </p>
              <p className="text-xs text-gray-600 mt-0.5">Editar via API (PUT /settings preferred_regions)</p>
            </div>
          </div>
        </div>
      </div>

      {/* --- Autonomía --- */}
      <div className={SECTION_STYLE} style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}>
        <div className={SECTION_HEADER} style={{ borderColor: "#1E2A3A" }}>
          <h2 className="text-sm font-semibold text-gray-300">Autonomía del cazador (M9.4)</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Cuánta libertad tiene SourceDiscoveryAgent para proponer fuentes nuevas.
          </p>
        </div>
        <div className="divide-y divide-[#1E2A3A]">
          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Auto-discovery habilitado</p>
              <p className="text-xs text-gray-600 mt-0.5">
                Si está ON el cron diario llama POST /sources/discover automáticamente.
              </p>
            </div>
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={settings.auto_discovery_enabled}
                onChange={(e) => save({ auto_discovery_enabled: e.target.checked })}
              />
              <div className="w-11 h-6 bg-gray-700 peer-checked:bg-cyan-600 rounded-full peer transition-colors relative">
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform peer-checked:translate-x-5"
                  style={{
                    transform: settings.auto_discovery_enabled ? "translateX(20px)" : "translateX(0)",
                  }}
                />
              </div>
            </label>
          </div>

          <div className={FIELD_ROW}>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">Máximo de fuentes nuevas / semana</p>
              <p className="text-xs text-gray-600 mt-0.5">Safety brake — entre 0 y 50.</p>
            </div>
            <input
              type="number"
              min={0}
              max={50}
              className={INPUT_BASE + " w-20 text-right"}
              value={settings.max_new_sources_per_week}
              onChange={(e) =>
                save({ max_new_sources_per_week: Math.max(0, Math.min(50, parseInt(e.target.value || "0", 10))) })
              }
            />
          </div>
        </div>
      </div>

      {/* Version info */}
      <div className="flex items-center justify-between text-xs text-gray-600">
        <span>circles-ai.ai Dashboard · M9.1 settings live</span>
        <span>updated_at {new Date(settings.updated_at * 1000).toLocaleString()}</span>
      </div>
    </div>
  );
}
