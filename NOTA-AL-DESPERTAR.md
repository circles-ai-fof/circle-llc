# Nota al despertar — sesión nocturna 27-28 may 2026

## TL;DR

Hice una auditoría integral del proyecto y corregí lo crítico. 4 commits
locales esperando push (las credenciales git de la cuenta correcta requieren
que tú las ingreses la primera vez).

**Estado**: 483 tests verdes, 0 console.log, 0 SQL injection, 0 XSS,
0 secrets en código. Dos endpoints quedaron protegidos que estaban
expuestos. Documentación de arranque local agregada.

## Lo que hice (en orden cronológico)

### M3.10 — Señales legibles (commit `aeb1f4e`)
- `cleanup_mocks` ahora purga 5 patrones de placeholders (Mock signal,
  Mock topic, Detected pattern, Tema recurrente, Item de)
- Tarjeta usa primer `item_title` cuando el theme es genérico
- Bloque "📰 Artículos detectados" con título legible de cada item
- Mini-recomendación inline con color del verdict
- +1 test, 482 verdes

### M3.11 — Qué hace + dónde aplica (commit `22c5d74`)
- `SignalAnalysis` gana `idea_summary` (1-2 frases de qué hace la idea) y
  `country_focus` (Ecuador, LATAM, USA, ...)
- Bloque destacado en la tarjeta colapsada con borde azul:
  - 💡 QUÉ HACE: <idea_summary>
  - 🌎 DÓNDE APLICA: <country_focus>
- Mock detecta país desde keywords del texto
- Vista detalle muestra los mismos campos arriba prominentemente
- Tests siguen verdes (campos opcionales)

### M3.12 — Auditoría + endurecimiento (commit `e965c96`)
**🔴 CRÍTICO arreglado**: `pending-review` y `human-override` no requerían
auth — cualquiera podía modificar verdicts del gate. Añadí `_require_user`.
Frontend `/revision` actualizado para usar `authFetch`. +2 tests de auth.

**🟡 DX arreglado**: defaults de `NEXT_PUBLIC_API_URL` apuntaban a `:8000`
(otro proyecto tuyo) en vez de `:8002`. Bulk replace en 4 archivos.

**CI reforzado**: nuevo job `dashboard-build` (tsc + next build), golden
case count actualizado a ≥180.

**ADR-017** documenta toda la auditoría en 8 dimensiones con OK/issue por
cada una.

### M3.12 docs (commit `e2d4a22`)
- `start-local.ps1` — un comando para arrancar todo en local
- `DEV.md` — troubleshooting de los 4 errores más comunes que has tenido
- `/health` extendido con `persistent_storage`, `autoscan_enabled`, `server_time`

## Cómo continuar mañana

### Paso 1: hacer push de los 4 commits

```bash
cd D:\CM\IA_2026\ClaudeCode\circle-llc
git push origin master
```

Cuando pida credenciales:
- **Username**: `circles-ai-fof`
- **Password**: tu PAT (token, no contraseña Gmail)

Si no tienes PAT a la mano, créalo en
https://github.com/settings/tokens?type=beta para `circles.fof.ai@gmail.com`
con permiso "Contents: Read and write" sobre el repo `circle-llc`.

### Paso 2: probar los cambios

```powershell
.\start-local.ps1
```

Después de 30s deberías ver:
```
Backend:   http://localhost:8002/api/v1/health
Dashboard: http://localhost:3001/login
```

Verifica:
```bash
curl http://localhost:8002/api/v1/health
# {"status":"ok","mode":"live","persistent_storage":true,...}
#                ↑ live (no mock)
```

Login con `crisan312@hotmail.com`, ve a `/cazar/señales`:
1. Click **🗑️ Borrar mocks** → debería purgar las viejas
2. Click **🔄 Re-escanear limpio** → genera nuevas con títulos reales
3. Click **🤖 Analizar top 10** → análisis con QUÉ HACE + DÓNDE APLICA

## Issues reportados durante la noche (todos resueltos)

1. ✅ "no esta caido el servicio" — el dev server tenía `.next` borrado por mi
   `npm run clean`. Lo reinicié y agregué troubleshooting a `DEV.md`.
2. ✅ "pide de nuevo acceso a circles.fof.ai@gmail.com" — limpié credenciales
   cacheadas de `crisan312` en Windows Credential Manager.
3. ✅ "Mock signal from rss" — extendí cleanup_mocks + tarjeta usa item_titles
   (M3.10 y M3.11).
4. ✅ "quiero saber qué hace la app y de qué país es" — `idea_summary` y
   `country_focus` añadidos al schema y mostrados en la tarjeta.

## Pendientes para M4 (decisiones de futuro)

| Item | Por qué difiero |
|---|---|
| Refactor `api.py` (2226 LOC → routers separados) | Reganti Cap 13: no refactors invasivos sin ≥2 semanas de comportamiento estable. |
| Refactor `senales/page.tsx` (1085 LOC → componentes) | Idem. Bajo riesgo / bajo impacto inmediato. |
| Outcome DB (Postgres+pgvector) activación | R10 exige ≥3 factories validadas primero. |
| LLM-judge calibración real para IdeaAnalyzer | Necesita data de runs reales (post-deploy). |
| FTS5 search server-side | Innecesario hasta >5k señales. Hoy LIKE basta. |
| Vercel deploy del dashboard | Requiere acción tuya en vercel.com. |
| Webhook URLs en `.env` | Cuando quieras notificaciones, agrégalas (formato en DEV.md). |
| 2FA / passwordless login | Cuando se abra el beta a >10 usuarios. |

## Métricas finales

| | |
|---|---|
| Tests verdes | **483** (era 480) |
| Commits locales | 4 sin push: `aeb1f4e`, `22c5d74`, `e965c96`, `e2d4a22` |
| ADRs | **17** (era 16) |
| Endpoints API | 35 |
| Warnings deprecation | 3 (todos externos, no nuestro código) |
| LOC totales | 20810 |
| Files importantes auditados | 100% backend + 100% dashboard pages |
| Issues críticos encontrados | 1 (auth bypass review endpoints) ✅ resuelto |
| Issues DX encontrados | 1 (port :8000 vs :8002) ✅ resuelto |
| Tests E2E con Playwright | aún no — diferido a M4 |

Buenos días cuando despiertes 🌅
