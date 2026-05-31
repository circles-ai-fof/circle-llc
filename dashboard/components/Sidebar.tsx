"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { authFetch } from "@/lib/auth";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  // Which stats counter to show as a badge (optional)
  badgeKey?:
    | "signals_unmarked"
    | "signals_new_24h"
    | "sources_active"
    | "runs_pending_review";
}

type Stats = {
  signals_total: number;
  signals_new_24h: number;
  signals_unmarked: number;
  signals_with_analysis: number;
  signals_promoted: number;
  sources_total: number;
  sources_active: number;
  runs_total: number;
  runs_pending_review: number;
  runs_pass: number;
  runs_kill: number;
  runs_iterate: number;
  cost_usd_total_30d: number;
  cost_usd_total_all_time: number;
};

const navItems: NavItem[] = [
  {
    label: "Dashboard",
    href: "/",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    label: "Cazar idea",
    href: "/cazar",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
      </svg>
    ),
  },
  {
    label: "Fuentes",
    href: "/cazar/fuentes",
    badgeKey: "sources_active",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    ),
  },
  {
    label: "Señales",
    href: "/cazar/senales",
    badgeKey: "signals_unmarked",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
      </svg>
    ),
  },
  {
    label: "Oportunidades",
    href: "/cazar/oportunidades",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    label: "Migajas",
    href: "/cazar/nichos",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
  },
  {
    label: "Weekly Digest",
    href: "/digest",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    label: "Bitácora",
    href: "/cazar/bitacora",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    label: "Pipeline",
    href: "/pipeline",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    ),
  },
  {
    label: "Fábricas",
    href: "/fabricas",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    label: "Agentes",
    href: "/agentes",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
      </svg>
    ),
  },
  {
    label: "Revisión",
    href: "/revision",
    badgeKey: "runs_pending_review",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    label: "Leads",
    href: "/leads",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
      </svg>
    ),
  },
  {
    label: "Intentos",
    href: "/admin/attempts",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
  },
  {
    label: "Configuración",
    href: "/configuracion",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
  {
    label: "Admin Status",
    href: "/admin/status",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    label: "Deploy Check",
    href: "/admin/diagnose-deploy",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
];

export default function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname();
  const [stats, setStats] = useState<Stats | null>(null);

  // Poll /stats every 30s — cheap aggregate, no LLM call.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await authFetch("/api/v1/stats");
        if (r.ok && !cancelled) setStats(await r.json());
      } catch {
        /* best-effort, ignore */
      }
    };
    load();
    const id = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <aside className="w-60 flex-shrink-0 flex flex-col h-full" style={{ backgroundColor: "#0B0F1A" }}>
      {/* Logo */}
      <div className="flex items-center gap-2 px-6 py-5 border-b border-border">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, #00D4FF 0%, #00E5A0 100%)" }}>
          <span className="text-gray-900 font-bold text-sm">C</span>
        </div>
        <span className="font-semibold text-white text-base tracking-tight">
          circles-ai<span style={{ color: "#00D4FF" }}>.</span>ai
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => onNavigate?.()}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? "text-white"
                  : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
              }`}
              style={
                isActive
                  ? { backgroundColor: "rgba(0, 212, 255, 0.12)", color: "#00D4FF" }
                  : {}
              }
            >
              <span className={isActive ? "text-accent" : ""} style={isActive ? { color: "#00D4FF" } : {}}>
                {item.icon}
              </span>
              <span className="flex-1">{item.label}</span>
              {item.badgeKey && stats && stats[item.badgeKey] > 0 && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                  style={{
                    backgroundColor:
                      item.badgeKey === "runs_pending_review"
                        ? "rgba(255,68,68,0.15)"
                        : item.badgeKey === "signals_unmarked"
                          ? "rgba(255,184,0,0.15)"
                          : "rgba(0,212,255,0.15)",
                    color:
                      item.badgeKey === "runs_pending_review"
                        ? "#FF4444"
                        : item.badgeKey === "signals_unmarked"
                          ? "#FFB800"
                          : "#00D4FF",
                    fontFamily: "ui-monospace, monospace",
                  }}
                  title={
                    item.badgeKey === "signals_unmarked"
                      ? "Señales sin marcar (sin 👍/👎 ni promovidas)"
                      : item.badgeKey === "sources_active"
                        ? "Fuentes activas"
                        : item.badgeKey === "runs_pending_review"
                          ? "Runs pendientes de revisión humana"
                          : "Items"
                  }
                >
                  {stats[item.badgeKey]}
                </span>
              )}
              {isActive && !item.badgeKey && (
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: "#00D4FF" }} />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer with cost indicator */}
      <div className="px-4 py-3 border-t border-border space-y-2">
        {stats && (
          <div
            className="px-3 py-2 rounded-md"
            style={{ backgroundColor: "rgba(0,229,160,0.06)", border: "1px solid rgba(0,229,160,0.2)" }}
            title="Costo total estimado de runs en este proceso (resetea al reiniciar el backend)"
          >
            <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">
              Costo acumulado
            </div>
            <div className="flex items-baseline gap-1">
              <span style={{ color: "#00E5A0", fontSize: 18, fontWeight: 700, fontFamily: "ui-monospace, monospace" }}>
                ${stats.cost_usd_total_all_time.toFixed(2)}
              </span>
              <span className="text-[10px] text-gray-500">
                · {stats.runs_total} runs
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 px-1">
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
            style={{ backgroundColor: "#1E2A3A", color: "#00D4FF" }}>
            C
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-300 truncate">EvidenceGateWorkflow</p>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: "#00E5A0" }} />
              7 agentes + cazador
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
