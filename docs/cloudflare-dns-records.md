# Cloudflare DNS Records — circles-ai.ai

> Registros DNS a configurar en Cloudflare para conectar el dashboard (Vercel)
> y opcionalmente el backend (Railway) al dominio `circles-ai.ai`.
>
> **Zona:** `circles-ai.ai`
> **Nameservers actuales:** `lady.ns.cloudflare.com`, `joel.ns.cloudflare.com`
> **Modo de uso:** Cloudflare → DNS → **Import and Export** → **Import DNS Records**
>                  (o agregar manualmente con la tabla de abajo)

---

## ⚡ Opción A — Import automático (BIND zone file)

Copiá este bloque a un archivo `.txt` y subilo en Cloudflare → DNS → **Import and Export** → **Import**.
Cloudflare detectará los registros y los agregará en bulk.

```bind
;; Circle LLC — Factory of Factories — DNS records for circles-ai.ai
;; Generated 2026-06-01 — Cristian Molina

;; ─── DASHBOARD (Vercel) ──────────────────────────────────────────────────
;; Subdomain → Next.js dashboard deployed en Vercel project "dashboard"
;; Vercel cuenta: crisan312s-projects
;; Production URL actual: dashboard-rose-one-97.vercel.app
dashboard.circles-ai.ai. 1 IN CNAME cname.vercel-dns.com.

;; ─── API BACKEND (Railway) ── (OPCIONAL pero recomendado) ───────────────
;; Subdomain → FastAPI orchestrator hosted en Railway
;; Railway project: circle-llc / service: circle-llc-backend
;; URL actual: circle-llc-backend-production.up.railway.app
api.circles-ai.ai. 1 IN CNAME circle-llc-backend-production.up.railway.app.
```

> **Nota:** el TTL=`1` significa "Automatic" en Cloudflare (≈300s en práctica).
> Cloudflare ignora valores de TTL en imports y los pone a Auto por defecto.

---

## 🖱 Opción B — Agregar manualmente en la UI

Si preferís crearlos uno a uno en Cloudflare → DNS → **Add record**:

### Registro 1 — Dashboard (OBLIGATORIO)

| Campo | Valor |
|---|---|
| **Type** | `CNAME` |
| **Name** | `dashboard` |
| **Target** | `cname.vercel-dns.com` |
| **Proxy status** | 🔘 **DNS only** (nube **gris**) |
| **TTL** | Auto |
| **Comment** | `Vercel dashboard — Circle LLC FoF` |

### Registro 2 — API Backend (OPCIONAL)

| Campo | Valor |
|---|---|
| **Type** | `CNAME` |
| **Name** | `api` |
| **Target** | `circle-llc-backend-production.up.railway.app` |
| **Proxy status** | 🔘 **DNS only** (nube **gris**) |
| **TTL** | Auto |
| **Comment** | `Railway backend — Circle LLC FoF` |

---

## ⚠️ Reglas críticas

### 1. Proxy DEBE estar en gris (DNS only)

Para AMBOS registros, el icono de la nube tiene que estar **gris** (DNS only), NO naranja (proxied).

**Por qué:**
- Vercel y Railway provisionan certificados SSL automáticamente vía Let's Encrypt
- Si Cloudflare proxy está activo (naranja), intercepta el handshake y rompe la validación
- Con proxy gris, Cloudflare solo resuelve el DNS y deja pasar tráfico directo

### 2. NO toques los registros existentes

La zona ya tiene records para:
- `circles-ai.ai` (apex) — landing en Vercel (`64.29.17.65`, `216.198.79.65`)
- `www.circles-ai.ai` — landing alias

**No los borres ni modifiques.** Sólo agregás los nuevos arriba.

### 3. Si CF te avisa "record conflicts"

Significa que ya existe un registro con el mismo nombre. Verificá antes:
```
dig dashboard.circles-ai.ai
dig api.circles-ai.ai
```
Si retornan NXDOMAIN → procedé. Si retornan algo → revisá ese record en CF antes de agregar.

---

## 🚀 Pasos completos end-to-end

1. **Cloudflare** → Login → seleccionar zona `circles-ai.ai`
2. Tab **DNS** → **Records** → (opcional) **Import and Export** para Opción A
3. Crear los 1 o 2 records de arriba
4. Verificar propagación (~30 segundos – 5 min):
   ```bash
   dig dashboard.circles-ai.ai +short
   # Esperado: cname.vercel-dns.com.
   #          76.76.21.21 (o IPs de Vercel)
   ```
5. **Decime "DNS listo"** y yo corro desde el CLI:
   ```bash
   # Para el dashboard
   cd dashboard && vercel domains add dashboard.circles-ai.ai

   # Para el backend (si agregaste api.circles-ai.ai)
   railway domain --custom api.circles-ai.ai
   ```
6. Vercel/Railway emiten cert SSL automático (~30 s)
7. Actualizo Railway envs:
   ```bash
   railway variables --set 'EXTRA_ALLOWED_ORIGINS=https://dashboard.circles-ai.ai'
   railway variables --set 'DASHBOARD_URL=https://dashboard.circles-ai.ai'
   ```
8. Actualizo Vercel env si agregaste API custom:
   ```bash
   vercel env rm NEXT_PUBLIC_API_URL production
   echo 'https://api.circles-ai.ai' | vercel env add NEXT_PUBLIC_API_URL production
   vercel deploy --prod --yes
   ```
9. Smoke test final:
   ```bash
   curl https://dashboard.circles-ai.ai/login                  # → 200
   curl https://api.circles-ai.ai/api/v1/health                # → {"status":"ok"}
   ```

---

## 📊 URLs finales esperadas

| Servicio | URL custom | URL provider (siempre disponible) |
|---|---|---|
| Landing | https://circles-ai.ai | (mismo) |
| Dashboard | https://dashboard.circles-ai.ai | https://dashboard-rose-one-97.vercel.app |
| API | https://api.circles-ai.ai | https://circle-llc-backend-production.up.railway.app |
| Docs API | https://api.circles-ai.ai/docs | https://circle-llc-backend-production.up.railway.app/docs |

---

## 🔧 Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| Vercel dice "Invalid Configuration" | Proxy está naranja | Pasalo a gris (DNS only) |
| `dig` no resuelve después de 10 min | TTL alto del NXDOMAIN cacheado | Flush DNS local: `ipconfig /flushdns` |
| Cert SSL no se emite | Apex en otra cuenta Vercel | Vercel pedirá un TXT verification — te lo paso para agregar |
| Dashboard carga pero CORS error | Railway env no actualizada | Re-ejecutar paso 7 |
| 502 Bad Gateway en api.circles-ai.ai | Railway custom domain pendiente | Esperar ~2 min tras `railway domain --custom` |

---

## 📁 Archivo plano BIND (para import)

Si querés solo el bloque para subir a Cloudflare, está separado en
[`cloudflare-zone.bind`](./cloudflare-zone.bind) en este mismo directorio.

---

_Generado el 2026-06-01 — Cristian Molina (Circle LLC)_
