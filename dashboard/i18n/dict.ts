// M8.1 — Diccionario i18n lightweight (sin librerías externas).
// Solo aplicamos a strings de UI navegacional + admin/exec pages.
// El contenido de signals/runs/ideas se mantiene en su idioma original
// (los matices de negocio se perderían en auto-traducción).

export type Locale = "es" | "en";

export const DICT = {
  // Sidebar
  "nav.dashboard": { es: "Overview", en: "Overview" },
  "nav.cazar": { es: "Cazar", en: "Hunt" },
  "nav.fuentes": { es: "Fuentes", en: "Sources" },
  "nav.senales": { es: "Señales", en: "Signals" },
  "nav.oportunidades": { es: "Oportunidades", en: "Opportunities" },
  "nav.nichos": { es: "Migajas", en: "Niches" },
  "nav.bitacora": { es: "Bitácora", en: "Logbook" },
  "nav.fabricas": { es: "Fábricas", en: "Factories" },
  "nav.agentes": { es: "Agentes", en: "Agents" },
  "nav.pipeline": { es: "Pipeline", en: "Pipeline" },
  "nav.revision": { es: "Revisión", en: "Review" },
  "nav.leads": { es: "Leads", en: "Leads" },
  "nav.intentos": { es: "Intentos", en: "Attempts" },
  "nav.configuracion": { es: "Configuración", en: "Settings" },
  "nav.analytics": { es: "Analytics", en: "Analytics" },
  "nav.digest": { es: "Resumen Semanal", en: "Weekly Digest" },
  "nav.admin_status": { es: "Estado Admin", en: "Admin Status" },
  "nav.deploy_check": { es: "Verificar Deploy", en: "Deploy Check" },
  "nav.logout": { es: "Cerrar sesión", en: "Log out" },

  // Common UI
  "common.refresh": { es: "Refrescar", en: "Refresh" },
  "common.loading": { es: "Cargando…", en: "Loading…" },
  "common.error": { es: "Error", en: "Error" },
  "common.search": { es: "Buscar…", en: "Search…" },
  "common.filter": { es: "Filtrar", en: "Filter" },
  "common.export": { es: "Exportar", en: "Export" },
  "common.cancel": { es: "Cancelar", en: "Cancel" },
  "common.save": { es: "Guardar", en: "Save" },
  "common.delete": { es: "Eliminar", en: "Delete" },
  "common.confirm": { es: "Confirmar", en: "Confirm" },
  "common.no_data": { es: "Sin data todavía", en: "No data yet" },
  "common.total": { es: "Total", en: "Total" },
  "common.signals": { es: "Señales", en: "Signals" },
  "common.runs": { es: "Runs", en: "Runs" },
  "common.cost": { es: "Costo", en: "Cost" },

  // Home / Overview
  "home.title": { es: "Overview", en: "Overview" },
  "home.subtitle": { es: "Factory of Factories — EvidenceGateWorkflow", en: "Factory of Factories — EvidenceGateWorkflow" },
  "home.new_factory": { es: "Nueva fábrica", en: "New factory" },
  "home.recent_runs": { es: "Runs recientes", en: "Recent runs" },
  "home.no_runs_yet": { es: "Aún no hay runs ejecutados", en: "No runs executed yet" },
  "home.launch_first": { es: "+ Lanzar primera fábrica", en: "+ Launch first factory" },
  "home.kpi_signals": { es: "Señales capturadas", en: "Signals captured" },
  "home.kpi_promoted": { es: "Promovidas a runs", en: "Promoted to runs" },
  "home.kpi_sources": { es: "Fuentes activas", en: "Active sources" },
  "home.kpi_pending_review": { es: "Pendientes de revisión", en: "Pending review" },

  // Login
  "login.title": { es: "Acceso closed-beta", en: "Closed-beta access" },
  "login.email_label": { es: "Email", en: "Email" },
  "login.email_placeholder": { es: "tu@email.com", en: "you@email.com" },
  "login.submit": { es: "Entrar", en: "Sign in" },
  "login.not_allowed": { es: "Tu email no está en la lista de beta. Te avisaremos cuando esté disponible.", en: "Your email is not on the beta list. We'll notify you when available." },

  // Analytics
  "analytics.title": { es: "Analytics", en: "Analytics" },
  "analytics.subtitle": { es: "Vista ejecutiva: signals/runs/cost por día + tops + feedback distribution.", en: "Executive view: signals/runs/cost per day + tops + feedback distribution." },
  "analytics.window": { es: "Ventana:", en: "Window:" },
  "analytics.days_7": { es: "7 días", en: "7 days" },
  "analytics.days_30": { es: "30 días", en: "30 days" },
  "analytics.days_90": { es: "90 días", en: "90 days" },
  "analytics.days_180": { es: "180 días", en: "180 days" },
  "analytics.kpi_signals_new": { es: "Señales nuevas", en: "New signals" },
  "analytics.kpi_runs_executed": { es: "Runs ejecutados", en: "Runs executed" },
  "analytics.kpi_pass_rate": { es: "Pass rate", en: "Pass rate" },
  "analytics.kpi_total_cost": { es: "Costo total LLM", en: "Total LLM cost" },
  "analytics.signals_per_day": { es: "📡 Señales capturadas por día", en: "📡 Signals captured per day" },
  "analytics.runs_per_day": { es: "🏭 Runs ejecutados por día", en: "🏭 Runs executed per day" },
  "analytics.verdicts_per_day": { es: "🎯 Verdicts por día (PASS / ITERATE / KILL)", en: "🎯 Verdicts per day (PASS / ITERATE / KILL)" },
  "analytics.cost_per_day": { es: "💰 Costo LLM por día (USD)", en: "💰 LLM cost per day (USD)" },
  "analytics.top_topics": { es: "🏷️ Top topics (suggested_topic)", en: "🏷️ Top topics (suggested_topic)" },
  "analytics.top_sources": { es: "📰 Top fuentes por señales", en: "📰 Top sources by signal count" },
  "analytics.feedback_dist": { es: "👍 Distribución de feedback", en: "👍 Feedback distribution" },
  "analytics.unmarked": { es: "Sin marcar", en: "Unmarked" },

  // Admin Status
  "admin.title": { es: "Admin Status", en: "Admin Status" },
  "admin.subtitle": { es: "Estado interno del sistema: agentes, env vars, crons, stats.", en: "Internal system state: agents, env vars, crons, stats." },
  "admin.mode": { es: "Modo", en: "Mode" },
  "admin.storage": { es: "Storage", en: "Storage" },
  "admin.agents": { es: "Agentes", en: "Agents" },
  "admin.sources": { es: "Fuentes", en: "Sources" },
  "admin.signals": { es: "Señales", en: "Signals" },
  "admin.runs": { es: "Runs", en: "Runs" },
  "admin.cors_origins": { es: "CORS origins", en: "CORS origins" },
  "admin.allowlist_emails": { es: "Allowlist emails", en: "Allowlist emails" },
  "admin.agents_registered": { es: "🤖 Agentes registrados", en: "🤖 Registered agents" },
  "admin.env_vars": { es: "🔐 Variables de entorno", en: "🔐 Environment variables" },
  "admin.crons": { es: "⏰ Crons configurados", en: "⏰ Configured crons" },

  // Deploy Diagnostic
  "deploy.title": { es: "Deploy Diagnostic", en: "Deploy Diagnostic" },
  "deploy.subtitle": { es: "Detecta misconfig común antes de despliegue: env vars, CORS, SMTP, cron.", en: "Detects common misconfig before deployment: env vars, CORS, SMTP, cron." },
  "deploy.status_ready": { es: "LISTO PARA PRODUCCIÓN", en: "READY FOR PRODUCTION" },
  "deploy.status_warnings": { es: "FUNCIONA CON DEGRADACIÓN", en: "WORKS WITH DEGRADATION" },
  "deploy.status_errors": { es: "NO LISTO — CORREGIR ERRORES", en: "NOT READY — FIX ERRORS" },
  "deploy.zero_issues": { es: "✓ Cero issues detectados. Sistema completamente configurado.", en: "✓ Zero issues detected. System fully configured." },
  "deploy.fix_label": { es: "Fix:", en: "Fix:" },

  // Digest
  "digest.title": { es: "Weekly Digest", en: "Weekly Digest" },
  "digest.subtitle": {
    es: "Resumen semanal automático: stats + top oportunidades + nichos + eventos + trending. Sin LLM (costo $0).",
    en: "Automatic weekly summary: stats + top opportunities + niches + events + trending. No LLM (cost $0).",
  },
  "digest.copy_html": { es: "📋 Copiar HTML", en: "📋 Copy HTML" },
  "digest.copy_html_done": { es: "✓ Copiado", en: "✓ Copied" },
  "digest.download_html": { es: "💾 Descargar .html", en: "💾 Download .html" },
  "digest.view_text": { es: "📝 Ver versión texto plano", en: "📝 View plain text version" },
  "digest.send_now": { es: "📨 Enviar ahora", en: "📨 Send now" },
  "digest.sending": { es: "Enviando…", en: "Sending…" },
};

export type DictKey = keyof typeof DICT;

const STORAGE_KEY = "circle.locale";
const DEFAULT_LOCALE: Locale = "es";

/**
 * Lee el locale activo desde localStorage. Default: es.
 * Safe para SSR — retorna default si window no existe.
 */
export function getLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "es" || stored === "en") return stored;
  } catch {
    /* localStorage bloqueado o lleno */
  }
  return DEFAULT_LOCALE;
}

export function setLocale(loc: Locale): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, loc);
  } catch {
    /* noop */
  }
}

/**
 * Traduce una key del diccionario al locale activo. Si la key no existe,
 * retorna la key cruda (fail-soft).
 */
export function t(key: DictKey, locale?: Locale): string {
  const loc = locale ?? getLocale();
  const entry = DICT[key];
  if (!entry) return key as string;
  return entry[loc] ?? entry.es ?? (key as string);
}
