# Arquitectura de seguridad — circle-llc (M3.17)

Auditoría completa solicitada por el founder. Cubre auth, autorización,
modelo de datos, headers, CORS, y sugerencias para hardening adicional.

## 1. Modelo actual de auth + aislamiento

### Single-tenant (M3)

Hoy la app es **single-tenant**: una sola instancia de SQLite con todas
las señales/runs/fuentes mezcladas. La auth funciona así:

```
Email allowlist (ALLOWED_EMAILS en .env)
   ↓
POST /api/v1/auth/login {email}
   ↓
Bearer token (TTL 14 días) en sessions table
   ↓
_require_user(request) en cada handler protegido
   ↓
Si token válido → acceso a TODA la data
```

**Implicación**: cualquier usuario en la allowlist puede ver las señales
de cualquier otro. Si dos founders comparten la misma instancia, comparten
señales.

Esto es OK mientras la closed beta sea de **3 personas que ya colaboran**
(crisan312, jfnunez, cristian.molina.ia.soporte). Si el founder onboarda
clientes a la misma instancia, **necesitará multi-tenancy** (sección 6).

### Permisos efectivos por endpoint

| Endpoint | Auth | Notas |
|---|---|---|
| `/health`, `/agents`, `/diagnostic` | público | safe — no expone PII ni decisiones |
| `/auth/login` | público | rate-limited |
| `/leads/capture` | público | 6 capas anti-bot (R26) |
| `/leads`, `/leads/stats` | `_is_admin` (X-Gate-Secret) | emails enmascarados sin secret |
| `/gate/run` | público + X-Gate-Secret opcional | ~$0.06/call, anti-bot expensive_llm tier |
| `/gate/runs/{id}` | público | URL es UUIDv4 (no enumerable) |
| `/gate/pending-review` | **_require_user** (M3.12) | era público, fixed |
| `/gate/runs/{id}/human-override` | **_require_user** (M3.12) | era público, fixed |
| `/signals/*`, `/sources/*`, `/stats`, `/links/*` | `_require_user` | todo M3 hunter |
| `/admin/*` | X-Gate-Secret | rescue endpoints |

### Anti-bot (R26 — 6 capas)

1. Honeypot field `company_website` (humanos nunca llenan)
2. Dwell time check (humanos >3000ms)
3. Cloudflare Turnstile (opt-in via env)
4. Disposable email blocklist
5. Rate limit por IP (3 tiers: public_form, login, expensive_llm)
6. Shared secret `X-Gate-Secret` (opt-in)

## 2. Headers HTTP (M3.17)

Implementados en `_security_headers` middleware:

| Header | Valor | Por qué |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | No MIME sniffing — browser respeta Content-Type |
| `X-Frame-Options` | `DENY` | Anti clickjacking (defense en profundidad junto a CSP frame-ancestors) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | No filtrar path/query a sitios externos |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Anti tracking |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | HSTS 2 años |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'` | API solo JSON — bloquea scripts/imgs |
| `X-XSS-Protection` | `0` | Deshabilita el legacy XSS auditor (atacable) |
| `Cross-Origin-Opener-Policy` | `same-origin` | Aísla browsing context (anti Spectre) |
| `Cross-Origin-Resource-Policy` | `same-origin` | Anti XS-Leaks |
| `Server` | `circles-ai` | No revelar Uvicorn version |

## 3. CORS

```python
allow_origins = [
    "https://circles-ai.ai",
    "https://www.circles-ai.ai",
    "https://dashboard.circles-ai.ai",
    "http://localhost:3000",      # dev landing
    "http://localhost:3001",      # dev dashboard
    "http://127.0.0.1:3000",
] + os.getenv("EXTRA_ALLOWED_ORIGINS", "").split(",")
allow_methods = ["GET", "POST", "OPTIONS"]
allow_headers = ["Content-Type", "Authorization", "X-Requested-With"]
allow_credentials = True
max_age = 600  # 10 min preflight cache
```

M3.17: el middleware **logea** intentos de cross-origin desde dominios no
allowlisted (audit log para detectar scraping desde sitios desconocidos).

**No se aceptan wildcards `*`** ni en origins ni en headers. Si añades un
nuevo origin, va a `EXTRA_ALLOWED_ORIGINS` en `.env` de Railway.

## 4. Base de datos — modelo de "RLS"

### SQLite no tiene RLS nativa

Postgres tiene `CREATE POLICY` con `ALTER TABLE … ENABLE ROW LEVEL
SECURITY`. SQLite NO. Si quieres aislamiento real por usuario en M3,
tienes 2 opciones:

#### Opción A: filtrar por user_email en cada query (cambio M3)

Costos: ~30 líneas en cada `*_store.list()` que filtran por user. Pero
HOY las tablas no tienen una columna `user_email` — habría que migrar
todas (signals, runs, sources, links_log).

Recomendación: **NO hacerlo ahora**. La closed beta es de 3 personas que
colaboran. Multi-tenancy real espera a M5 (cuando haya clientes externos).

#### Opción B: migrar a Postgres + RLS real (M5)

```sql
ALTER TABLE signals ADD COLUMN user_email TEXT NOT NULL;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY signals_isolation ON signals
  USING (user_email = current_setting('app.current_user', true));
```

Y en cada request: `SET app.current_user = '<email del token>'`. Postgres
hace cumplir el aislamiento aunque la app tenga un bug.

### Mientras tanto: salvaguardas single-tenant

En M3.12 (auditoría):
- ✅ Todos los endpoints sensibles tienen `_require_user`
- ✅ Login attempts se loggean con IP + user_agent para forensics
- ✅ Tokens expiran en 14 días
- ✅ `runs_store` persistente en SQLite con WAL mode

## 5. SQLite hardening

Actualmente:
- ✅ WAL mode (concurrent reads + 1 writer)
- ✅ Foreign keys con `ON DELETE SET NULL`
- ✅ Índices en columnas filtradas
- ✅ Parameterized queries (sin SQL injection)
- ✅ `.db` files en `.gitignore`
- ✅ DATABASE_PATH=/data en Railway (volume persistente)

Pendiente:
- ❌ Encrypted storage (SQLCipher) — overkill para closed beta
- ❌ Backup automático — pendiente M4 (Railway backups manuales por ahora)

## 6. Sugerencias adicionales

### 🟢 Alto valor / bajo esfuerzo (M3.17+)

1. **Backup automático nocturno** del SQLite a un bucket S3.
   El archivo está en `/data/circle_llc.db` (Railway volume). 1 línea de
   cron + 1 endpoint admin.

2. **2FA opcional vía email magic-link**. Hoy el login solo necesita el
   email; cualquiera con acceso al inbox puede entrar. Magic-link añade
   una capa (mostrar 6-digit code enviado al email).

3. **Audit log persistente** para acciones sensibles (override de verdict,
   eliminar fuentes en bulk, exportar CSV). Hoy se loggea a stdout pero
   no queda persistido para forensics.

4. **Rate limit por usuario** (no solo por IP) en endpoints que cobran
   LLM (`/analyze`, `/promote`). Hoy un user puede abusar desde 100 IPs
   distintas. Cap diario por user_email.

### 🟡 Mediano esfuerzo (M4)

5. **Postgres + RLS** cuando haya >5 users (sección 4B).

6. **Webhooks signing** con HMAC. Hoy los webhooks son fire-and-forget;
   si Slack/Zapier reciben datos sensibles deberían verificar que vienen
   de circle-llc (header `X-Webhook-Signature`).

7. **Cloudflare en frente de Railway** para WAF + DDoS + rate limit
   gratis. Apuntar `api.circles-ai.ai` a Cloudflare proxied.

### 🔵 Largo plazo (M5+)

8. **SOC 2 readiness** si vendes B2B a empresas. Hoy NO está preparado.

9. **Anonymización de runs** para que el outcome-db agregado no tenga PII.

10. **Penetration test externo** una vez al año cuando tengas ARR >$50k.

## 7. Lo que NO recomiendo

❌ Encriptar el .db (SQLCipher) — añade complejidad sin valor en este stage
❌ JWT en vez de token simple — más complejo, menos auditable
❌ OAuth con Google — innecesario para 3 usuarios
❌ Multi-region Postgres — millones de dólares de overkill
❌ Migrar a microservicios — Reganti Cap 1: "monolitos son válidos hasta
   que duela"

## 8. Verificación

Para chequear los headers en prod:

```bash
curl -sI https://circle-llc-production.up.railway.app/api/v1/health | grep -iE "x-|strict-|content-security|cross-origin"
```

Para chequear CORS:

```bash
curl -s -H "Origin: https://malicious.example.com" -i \
  https://circle-llc-production.up.railway.app/api/v1/health | grep -i access-control
# Debería NO devolver Access-Control-Allow-Origin (no allowlisted)
```

## 9. Resumen ejecutivo

| Capa | Estado | Acción recomendada |
|---|---|---|
| Auth allowlist | ✅ M3 | Mantener |
| Auth en endpoints sensibles | ✅ M3.12 | Audit periódico |
| Headers OWASP | ✅ M3.17 reforzado | — |
| CORS estricto | ✅ M3 + logging M3.17 | — |
| Anti-bot R26 | ✅ M2 | — |
| SQL injection | ✅ M1 | — |
| XSS / clickjacking | ✅ M3.17 | — |
| Aislamiento multi-tenant | ❌ single-tenant | Cuando >5 users → Postgres+RLS |
| Backup automático | ❌ manual | M3.17+ |
| 2FA | ❌ email-only login | M4 |
| Audit log persistente | 🟡 stdout | M4 |
| Pen test externo | ❌ | Cuando ARR >$50k |

**Riesgo residual aceptable**: para una closed beta de 3 personas que
colaboran sobre el mismo dataset, el modelo actual es razonable.
Reevaluar cuando: (a) onboarden clientes externos, (b) entren PII más
sensible (PIIs financieros, tarjetas), (c) lleguen amenazas reales
detectadas en el log.
