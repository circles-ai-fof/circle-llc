# Observabilidad de Agentes — Langfuse

## Decision tecnica

Se eligio **Langfuse** (open-source, Apache 2.0) como plataforma de observabilidad para los agentes del `EvidenceGateWorkflow`.

### Por que Langfuse y no Helicone

| Criterio | Langfuse | Helicone |
|---|---|---|
| Self-hostable | Si (Docker) | No (solo cloud) |
| Open-source | Si (Apache 2.0) | No |
| Cumplimiento LOPDP Ecuador | Si — datos permanecen en infra propia | No — datos en third-party cloud USA |
| Lock-in | Ninguno | Alto (API propietaria) |
| Agent-native (traces jerarquicos) | Si | Limitado |
| Costo largo plazo | $0 self-hosted | Por volumen |

Helicone fue descartado por incumplir la LOPDP Ecuador (Ley Organica de Proteccion de Datos Personales): los datos de prompts y outputs de agentes pueden contener informacion comercial sensible de Asiservy y de los usuarios finales de circles-ai.ai.

## Que se captura por trace

Cada llamada a `_call()` o `_call_with_tools()` en `BaseAgent` registra una `Generation` con:

| Campo | Descripcion |
|---|---|
| `name` | `NombreAgente._call` o `NombreAgente._call_with_tools` |
| `model` | modelo Anthropic usado (ej. `claude-sonnet-4-6`) |
| `input` | `user_message` enviado al LLM |
| `output` | texto de respuesta (o lista de tool_calls) |
| `usage.input` | tokens de entrada (para calculo de costo) |
| `usage.output` | tokens de salida |
| `metadata.agent` | nombre de la clase del agente |
| `metadata.tool_count` | numero de tools definidas (solo `_call_with_tools`) |
| `metadata.tool_calls_made` | numero de tool_use blocks retornados |
| latencia | Langfuse la calcula automaticamente desde `startTime`/`endTime` |

## Que NO se captura

- PII de usuarios finales (nombres, emails, datos de contacto)
- Datos brutos de clientes Asiservy
- Credenciales, API keys, tokens
- Contenido de archivos o uploads

El system prompt de cada agente SI se captura implicitamente via el bloque de sistema enviado al LLM. Asegurate de que el system prompt no contenga datos sensibles de produccion.

## Como activar

### Variables de entorno requeridas

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxx
# Opcional — default: https://cloud.langfuse.com
LANGFUSE_HOST=https://tu-instancia-langfuse.example.com
```

Si `LANGFUSE_PUBLIC_KEY` no esta definida, la instrumentacion se desactiva completamente (graceful degradation). Los agentes funcionan identico sin la variable.

### Verificar que esta activo

```python
from orchestrator.core.base_agent import _LANGFUSE_ENABLED
print(_LANGFUSE_ENABLED)  # True si la key esta en el env
```

## Como ver los traces

1. Abrir el dashboard de Langfuse (cloud o self-hosted)
2. Seccion **Generations** — cada llamada de agente aparece como una Generation
3. Filtrar por `metadata.agent` para ver trazas de un agente especifico
4. Seccion **Dashboard** para metricas agregadas

## Dashboard ejecutivo — 4 widgets recomendados

| Widget | Descripcion | Query sugerida |
|---|---|---|
| **Worst cases semanales** | Generaciones con mayor latencia P95 en los ultimos 7 dias | `ORDER BY latency DESC LIMIT 10, 7d` |
| **Costo P50/P95** | Distribucion de costo estimado por generacion (input+output tokens x precio modelo) | `PERCENTILE(cost, 0.5), PERCENTILE(cost, 0.95)` |
| **Eval scores** | Puntuaciones de evaluaciones LLM-as-judge si se configuran | `AVG(score) GROUP BY eval_name` |
| **Tool call success rate** | Porcentaje de `_call_with_tools` donde `tool_calls_made > 0` | `SUM(tool_calls_made > 0) / COUNT(*)` |

## Instancia self-hosted — ejemplo docker-compose

Agregar al `docker-compose.yml` del proyecto:

```yaml
services:
  langfuse-server:
    image: langfuse/langfuse:latest
    depends_on:
      - langfuse-db
    ports:
      - "3010:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: cambia-esto-en-produccion
      SALT: cambia-esto-en-produccion
      NEXTAUTH_URL: http://localhost:3010
      TELEMETRY_ENABLED: "false"
      LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES: "false"

  langfuse-db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - langfuse_db_data:/var/lib/postgresql/data

volumes:
  langfuse_db_data:
```

Luego en `.env`:
```bash
LANGFUSE_HOST=http://localhost:3010
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx   # generado en la UI de Langfuse
LANGFUSE_SECRET_KEY=sk-lf-xxxxx
```

## Separacion de responsabilidades

| Herramienta | Alcance |
|---|---|
| **Langfuse** | Trazas de agentes LLM: prompts, outputs, tokens, latencia, costos, evals |
| **Sentry** | Excepciones de infraestructura: DB caida, OAuth fail, errores 500 inesperados |
| **PostHog** | Analytics de landings publicas: clicks, conversion funnel, A/B tests de copy |

No usar Sentry para logica de agentes (falsos positivos, ruido). No usar PostHog para agentes (no es agent-native).
