# Agentes Deferidos — NO usar en Sprint M1

Estos agentes están deferidos hasta Mes 12+ cuando se cumplan los tres criterios documentados en `SCOPES.md`.

**Decisión:** AI Builder's Handbook Cap 15 §15.1 — "For 90% of enterprise AI teams, the right multi-agent answer is: not yet. Build workflows. Build single agents where workflows fall short."

Los 5 agentes activos en Sprint M1 cubren el 100% del flujo evidence-gate. Los agentes listados abajo resuelven problemas de fases posteriores (Sprint M2+).

---

## Agentes deferidos Sprint M2-M4 (construcción de fábrica)

| Agente (propuesto) | Función | Fase mínima para activar |
|---|---|---|
| `architect_agent` | Blueprint técnico C4, selección de stack | M2 (primera fábrica) |
| `developer_agent` | Generación de código, scaffolding | M2 |
| `qa_agent` | Red-teaming, edge cases, prompt injection | M2 |
| `devops_agent` | CI/CD, Dockerfile, infra-as-code | M2 |
| `db_schema_agent` | Diseño de esquemas SQL/pgvector | M2 |

## Agentes deferidos Sprint M5-M8 (operación de fábricas)

| Agente (propuesto) | Función | Fase mínima |
|---|---|---|
| `onboarding_agent` | Configura nueva fábrica desde template | M5 |
| `growth_agent` | Análisis de métricas de crecimiento | M5 |
| `support_agent` | Respuesta a tickets de usuarios | M6 |
| `pricing_agent` | Optimización de precios y planes | M6 |
| `retention_agent` | Análisis de churn y acciones | M7 |

## Agentes deferidos Sprint M9-M12 (cross-vertical intelligence)

| Agente (propuesto) | Función | Fase mínima |
|---|---|---|
| `insight_miner_agent` | Extrae patterns cross-factory del Outcome DB | M9 (N≥3 fábricas) |
| `playbook_generator_agent` | Genera playbooks de éxito desde insights | M10 |
| `factory_ranker_agent` | Prioriza ideas nuevas basado en histórico | M11 |
| `risk_detector_agent` | Detecta señales de fábrica en riesgo | M11 |
| `meta_optimizer_agent` | Optimiza el orquestador con sus propios datos | M12 |

## Agentes deferidos indefinidamente (requieren revisión de valor)

| Agente (propuesto) | Por qué deferido indefinidamente |
|---|---|
| `competitive_intel_agent` | Un workflow con web scraping determinista resuelve el 90% del caso |
| `social_media_agent` | Herramienta + template es suficiente — no justifica agente |
| `content_writer_agent` | `landing_generator` ya cubre el caso M1; M2+ se evalúa |
| `email_campaign_agent` | API determinista (SendGrid/Resend) — no necesita LLM en el loop |
| `legal_review_agent` | Liability demasiado alta sin red-teaming exhaustivo; deferido |

---

Para activar cualquier agente: crear un ADR en `orchestrator/decisions/` documentando:
1. El problema específico que el agente resuelve
2. Por qué un workflow o código determinista no lo resuelve
3. Los 30 golden cases del eval suite del agente
4. El costo estimado por corrida
