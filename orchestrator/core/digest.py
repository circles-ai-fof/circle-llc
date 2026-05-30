"""
M6.1 — Weekly digest builder.

Genera un resumen semanal de actividad del cazador + las oportunidades top:
- Stats: runs, signals capturadas, promovidas, pass rate
- Top 3 first-mover opportunities (de M4.11 cross_country_gaps)
- Top 3 nichos sub-explorados (de M4.15 niche_opportunities)
- Eventos relevantes recientes (signals kind=events)
- Trending searches con score alto (signals kind=google_trends)

Sin SMTP integrado — el send real queda a M6.2 cuando configures Mailgun/
SendGrid/Resend. Por ahora el founder accede a /digest en el dashboard o
hace curl al endpoint y copia-pega al cliente de email.

NO usa LLM. Heurística pura sobre datos existentes — costo $0.
"""
from __future__ import annotations

import html as _html
import time
from typing import Dict, List


def build_digest_data(window_days: int = 7) -> Dict:
    """Recolecta toda la data para el digest. Sin LLM, costo $0."""
    from .storage import signals_store, sources_store, runs_store

    cutoff = int(time.time()) - (window_days * 86_400)

    # ----- Stats agregados -----
    all_signals = signals_store.list(limit=10_000, min_score=0)
    signals_total = len(all_signals)
    signals_this_week = sum(1 for s in all_signals if s.get("created_at", 0) >= cutoff)
    signals_promoted = sum(1 for s in all_signals if s.get("promoted_run_id"))
    signals_with_up = sum(1 for s in all_signals if s.get("feedback") == "up")

    all_sources = sources_store.list()
    sources_active = sum(1 for s in all_sources if s.get("active"))

    all_runs = list(runs_store.values())
    runs_total = len(all_runs)
    runs_pass = sum(1 for r in all_runs if r.verdict == "pass")
    pass_rate = round(100 * runs_pass / runs_total, 1) if runs_total else 0.0

    # ----- Top oportunidades cross-country (M4.11) -----
    gaps = signals_store.cross_country_gaps(
        min_validation_signals=2, min_validation_feedback=1,
    )
    top_gaps = gaps[:3]

    # ----- Top nichos sub-explorados (M4.15) -----
    niches = signals_store.niche_opportunities(
        min_parent_size=5, max_niche_size=3, top_parents=3,
    )

    # ----- Eventos recientes (kind=events) con score >= 0.5 -----
    recent_events = [
        s for s in all_signals
        if s.get("source_kind") == "events"
        and s.get("created_at", 0) >= cutoff
        and (s.get("score") or 0) >= 0.5
    ]
    recent_events.sort(key=lambda s: s.get("created_at", 0), reverse=True)

    # ----- Trending searches (kind=google_trends) con score >= 0.5 -----
    recent_trends = [
        s for s in all_signals
        if s.get("source_kind") == "google_trends"
        and s.get("created_at", 0) >= cutoff
        and (s.get("score") or 0) >= 0.5
    ]
    recent_trends.sort(key=lambda s: s.get("score", 0), reverse=True)

    return {
        "generated_at": int(time.time()),
        "window_days": window_days,
        "stats": {
            "signals_total": signals_total,
            "signals_this_week": signals_this_week,
            "signals_promoted": signals_promoted,
            "signals_with_up": signals_with_up,
            "sources_active": sources_active,
            "runs_total": runs_total,
            "runs_pass": runs_pass,
            "pass_rate_pct": pass_rate,
        },
        "top_first_mover_gaps": [
            {
                "idea_summary": g["idea_summary"],
                "validated_in": [v["country"] for v in g["validated_in"]],
                "missing_in": g["missing_in"][:5],
                "opportunity_score": g["opportunity_score"],
            }
            for g in top_gaps
        ],
        "top_niches": [
            {
                "parent_market": n["parent_market"],
                "parent_size": n["parent_size"],
                "leader_topic": n["leader_niche"]["topic"],
                "underexplored": [u["topic"] for u in n["underexplored_niches"][:3]],
                "opportunity_count": n["opportunity_count"],
            }
            for n in niches
        ],
        "recent_events": [
            {
                "theme": s["theme"],
                "url": (s.get("evidence_urls") or [""])[0],
                "score": s.get("score", 0),
                "captured_at": s.get("created_at", 0),
            }
            for s in recent_events[:5]
        ],
        "recent_trends": [
            {
                "theme": s["theme"],
                "url": (s.get("evidence_urls") or [""])[0],
                "score": s.get("score", 0),
                "captured_at": s.get("created_at", 0),
            }
            for s in recent_trends[:5]
        ],
    }


def render_digest_html(data: Dict, dashboard_url: str = "http://localhost:3001") -> str:
    """Renderiza el digest como HTML autocontenido (email-ready inline styles)."""
    s = data["stats"]
    # Helpers
    def esc(x: object) -> str:
        return _html.escape(str(x))

    def link(href: str, text: str) -> str:
        return f'<a href="{esc(href)}" style="color:#00D4FF; text-decoration:none;">{esc(text)}</a>'

    # ----- Stats cards -----
    stats_html = (
        '<table cellspacing="8" cellpadding="0" border="0" style="width:100%; margin-bottom:24px;">'
        '<tr>'
        f'<td style="background:#0F1525; border:1px solid #1e293b; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Señales nuevas (7d)</div>'
        f'<div style="color:#00D4FF; font-size:22px; font-weight:700; margin-top:4px;">{s["signals_this_week"]}</div>'
        f'<div style="color:#64748b; font-size:10px;">de {s["signals_total"]} totales</div>'
        f'</td>'
        f'<td style="background:#0F1525; border:1px solid #1e293b; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">👍 marcadas</div>'
        f'<div style="color:#00E5A0; font-size:22px; font-weight:700; margin-top:4px;">{s["signals_with_up"]}</div>'
        f'</td>'
        f'<td style="background:#0F1525; border:1px solid #1e293b; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">🚀 promovidas</div>'
        f'<div style="color:#A78BFA; font-size:22px; font-weight:700; margin-top:4px;">{s["signals_promoted"]}</div>'
        f'</td>'
        f'<td style="background:#0F1525; border:1px solid #1e293b; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Pass rate</div>'
        f'<div style="color:#FFB800; font-size:22px; font-weight:700; margin-top:4px;">{s["pass_rate_pct"]}%</div>'
        f'<div style="color:#64748b; font-size:10px;">{s["runs_total"]} runs total</div>'
        f'</td>'
        '</tr>'
        '</table>'
    )

    # ----- First-mover gaps -----
    if data["top_first_mover_gaps"]:
        gaps_items = []
        for g in data["top_first_mover_gaps"]:
            validated = ", ".join(esc(v) for v in g["validated_in"])
            missing = ", ".join(esc(m) for m in g["missing_in"][:3])
            score_color = "#00E5A0" if g["opportunity_score"] >= 0.7 else "#FFB800"
            gaps_items.append(
                f'<div style="background:#0F1525; border:1px solid #1e293b; '
                f'border-left:3px solid {score_color}; border-radius:6px; '
                f'padding:12px; margin-bottom:8px;">'
                f'<div style="color:#fff; font-weight:600; margin-bottom:6px;">{esc(g["idea_summary"][:140])}</div>'
                f'<div style="color:#94a3b8; font-size:12px; margin-bottom:4px;">'
                f'  ✓ Validada en: <span style="color:#00E5A0;">{validated}</span>'
                f'</div>'
                f'<div style="color:#94a3b8; font-size:12px;">'
                f'  🚀 Gap en: <span style="color:#FF4444;">{missing}</span>'
                f'  <span style="color:#64748b; margin-left:8px;">'
                f'    score {int(g["opportunity_score"] * 100)}'
                f'  </span>'
                f'</div>'
                f'</div>'
            )
        gaps_html = "".join(gaps_items)
    else:
        gaps_html = (
            '<div style="color:#64748b; padding:12px; font-style:italic;">'
            'Sin oportunidades cross-country detectadas esta semana. '
            'Marca 👍 en señales prometedoras para que el detector las agrupe.'
            '</div>'
        )

    # ----- Niches -----
    if data["top_niches"]:
        niche_items = []
        for n in data["top_niches"]:
            underexplored = ", ".join(esc(u) for u in n["underexplored"][:3])
            niche_items.append(
                f'<div style="background:#0F1525; border:1px solid #1e293b; '
                f'border-left:3px solid #A78BFA; border-radius:6px; '
                f'padding:12px; margin-bottom:8px;">'
                f'<div style="color:#fff; font-weight:600; text-transform:capitalize; margin-bottom:6px;">'
                f'🏛️ {esc(n["parent_market"])} '
                f'<span style="color:#64748b; font-weight:400; font-size:11px;">'
                f'({n["parent_size"]} señales · {n["opportunity_count"]} migajas)'
                f'</span>'
                f'</div>'
                f'<div style="color:#FFB800; font-size:12px; margin-bottom:4px;">'
                f'  🥊 Líder: {esc(n["leader_topic"])}'
                f'</div>'
                f'<div style="color:#94a3b8; font-size:12px;">'
                f'  🍞 Migajas: <span style="color:#00E5A0;">{underexplored}</span>'
                f'</div>'
                f'</div>'
            )
        niches_html = "".join(niche_items)
    else:
        niches_html = (
            '<div style="color:#64748b; padding:12px; font-style:italic;">'
            'Sin nichos sub-explorados detectados. Ejecuta más scans para '
            'acumular volumen en mercados padre.'
            '</div>'
        )

    # ----- Events -----
    if data["recent_events"]:
        events_items = []
        for ev in data["recent_events"]:
            events_items.append(
                f'<li style="color:#cbd5e1; margin-bottom:6px;">'
                f'{esc(ev["theme"][:140])} '
                f'<span style="color:#64748b; font-size:11px;">'
                f'  (score {ev["score"]:.2f})'
                f'</span>'
                + (f' — {link(ev["url"], "ver →")}' if ev["url"] else '')
                + '</li>'
            )
        events_html = f'<ul style="padding-left:18px; margin:0;">{"".join(events_items)}</ul>'
    else:
        events_html = (
            '<div style="color:#64748b; padding:12px; font-style:italic;">'
            'Ningún evento detectado esta semana. Suscribite a feeds Lu.ma o '
            'Eventbrite en /cazar/fuentes (kind=events).'
            '</div>'
        )

    # ----- Trends -----
    if data["recent_trends"]:
        trends_items = []
        for tr in data["recent_trends"]:
            trends_items.append(
                f'<li style="color:#cbd5e1; margin-bottom:6px;">'
                f'{esc(tr["theme"][:140])} '
                f'<span style="color:#64748b; font-size:11px;">'
                f'  (score {tr["score"]:.2f})'
                f'</span>'
                + '</li>'
            )
        trends_html = f'<ul style="padding-left:18px; margin:0;">{"".join(trends_items)}</ul>'
    else:
        trends_html = (
            '<div style="color:#64748b; padding:12px; font-style:italic;">'
            'Sin trending searches esta semana. Suscribite a kind=google_trends '
            'por país para ver qué se está buscando.'
            '</div>'
        )

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>FoF Weekly Digest</title>
</head>
<body style="margin:0; padding:24px; background:#0B0F1A; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table cellspacing="0" cellpadding="0" border="0" style="max-width:680px; margin:0 auto; width:100%;">
<tr><td>

<div style="text-align:center; margin-bottom:32px;">
  <h1 style="color:#fff; margin:0 0 6px 0; font-size:26px;">📡 Factory of Factories — Resumen Semanal</h1>
  <div style="color:#94a3b8; font-size:13px;">
    Últimos {data["window_days"]} días · {link(dashboard_url, "Abrir dashboard")}
  </div>
</div>

<h2 style="color:#fff; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; margin:24px 0 8px 0;">
  📊 Actividad de la semana
</h2>
{stats_html}

<h2 style="color:#fff; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; margin:24px 0 8px 0;">
  🌎 Top oportunidades first-mover
</h2>
{gaps_html}

<h2 style="color:#fff; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; margin:24px 0 8px 0;">
  🍞 Migajas de gigantes
</h2>
{niches_html}

<h2 style="color:#fff; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; margin:24px 0 8px 0;">
  🎤 Eventos para considerar
</h2>
{events_html}

<h2 style="color:#fff; font-size:14px; text-transform:uppercase; letter-spacing:0.5px; margin:24px 0 8px 0;">
  💰 Trending searches con score alto
</h2>
{trends_html}

<div style="margin-top:40px; padding-top:16px; border-top:1px solid #1e293b; color:#64748b; font-size:11px; text-align:center;">
  Circle LLC · circles-ai.ai · Generado el {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(data["generated_at"]))}<br>
  {link(dashboard_url + "/cazar/oportunidades", "Ver oportunidades")} ·
  {link(dashboard_url + "/cazar/nichos", "Ver nichos")} ·
  {link(dashboard_url + "/cazar/senales", "Ver señales")}
</div>

</td></tr>
</table>
</body>
</html>'''


def render_digest_text(data: Dict) -> str:
    """Renderiza el digest como texto plano (fallback para emails sin HTML)."""
    s = data["stats"]
    lines = [
        "=" * 56,
        "FACTORY OF FACTORIES — RESUMEN SEMANAL",
        f"Últimos {data['window_days']} días",
        "=" * 56,
        "",
        "ACTIVIDAD DE LA SEMANA",
        f"  Señales nuevas: {s['signals_this_week']} (de {s['signals_total']} totales)",
        f"  👍 marcadas:    {s['signals_with_up']}",
        f"  🚀 promovidas:  {s['signals_promoted']}",
        f"  Pass rate:      {s['pass_rate_pct']}% ({s['runs_total']} runs)",
        f"  Fuentes activas: {s['sources_active']}",
        "",
        "TOP OPORTUNIDADES FIRST-MOVER",
    ]
    if data["top_first_mover_gaps"]:
        for g in data["top_first_mover_gaps"]:
            lines.append(f"  • {g['idea_summary'][:120]}")
            lines.append(f"    ✓ Validada en: {', '.join(g['validated_in'])}")
            lines.append(f"    🚀 Gap en: {', '.join(g['missing_in'][:3])}")
            lines.append(f"    Score: {int(g['opportunity_score'] * 100)}")
    else:
        lines.append("  (sin oportunidades esta semana — marca más 👍)")
    lines.extend(["", "MIGAJAS DE GIGANTES"])
    if data["top_niches"]:
        for n in data["top_niches"]:
            lines.append(f"  🏛️ {n['parent_market']} ({n['parent_size']} señales)")
            lines.append(f"    Líder: {n['leader_topic']}")
            lines.append(f"    Migajas: {', '.join(n['underexplored'][:3])}")
    else:
        lines.append("  (sin nichos detectados)")
    lines.extend(["", "EVENTOS RECIENTES"])
    if data["recent_events"]:
        for ev in data["recent_events"]:
            lines.append(f"  • {ev['theme'][:140]} (score {ev['score']:.2f})")
    else:
        lines.append("  (ninguno)")
    lines.extend(["", "TRENDING SEARCHES"])
    if data["recent_trends"]:
        for tr in data["recent_trends"]:
            lines.append(f"  • {tr['theme'][:140]} (score {tr['score']:.2f})")
    else:
        lines.append("  (ninguno)")
    lines.extend([
        "",
        "=" * 56,
        f"Circle LLC · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(data['generated_at']))}",
    ])
    return "\n".join(lines)
