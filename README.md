# Dev Lead Hunter 🎯

Bot "agresivo" que vigila redes sociales y portales 24/7 buscando **personas o negocios que NECESITAN un ingeniero de
software / sistemas** (no ofertas de empleo corporativo, no gente ofreciendo servicios) y te avisa **al instante en tu
celular por ntfy** con: resumen, score 0-100, link directo a la publicación y una frase sugerida para abrir conversación.

```
Fuentes ──► Dedup (SQLite) ──► Filtro keywords ES/EN ──► Gemini (IA) ──► ntfy 📲
 Facebook grupos (Bright Data) barato, 0 costo      is_lead / score / resumen / opener
 Facebook búsqueda (Apify)
 LinkedIn posts  (Apify)
 X / Twitter     (Apify)
 Freelancer.com  (gratis)
 Reddit          (gratis, si no está bloqueado)
 Telegram grupos (opcional)
```

Probado con datos reales: el POC detectó leads como *"Dueño de restaurante necesita plataforma de software con reservas"*,
*"Emprendedor necesita desarrollador web para tienda Shopify"*, y descartó correctamente ofertas de empleo y gente ofreciendo servicios.

---

## 1. ¿Por qué así? (decisiones importantes)

| Tema | Decisión | Por qué |
|---|---|---|
| **Facebook grupos** | **Bright Data** Web Scraper API (posts por grupo) | Lee los grupos que elijas, ~$0.0015 por post (3x más barato que Apify). 5000 créditos gratis/mes. Asíncrono: si tarda, el bot retoma el snapshot en la siguiente corrida sin volver a pagar. |
| **Facebook búsqueda / LinkedIn / X** | **Apify** (scraping como servicio) | **No usa tus credenciales → cero riesgo de que te baneen tu cuenta.** Solo lee grupos/posts PÚBLICOS. Plan gratis: $5 de créditos/mes. |
| **Freelancer.com** | API pública, sin key | Gratis e ilimitada. Todo lo que publica un cliente ahí es un pedido real de trabajo. Soporta español. |
| **Reddit** | JSON público, tolerante | Reddit cerró la creación self-service de apps (nov 2025) y bloquea IPs cloud. El bot lo intenta; si responde 403 lo pausa 6 h y sigue con el resto. **No rompe nada.** |
| **Nitter (X gratis)** | Descartado | En 2026 ya no quedan instancias funcionales. X solo por Apify. |
| **Workana / Upwork** | Descartados por ahora | Están detrás de Cloudflare. Se pueden agregar vía Apify si lo necesitas. |
| **IA** | Gemini `gemini-3.5-flash-lite` (gratis) | ~1000 clasificaciones/día gratis. Salida JSON estricta. Si se acaba la cuota → fallback automático a keywords. |
| **Notificaciones** | ntfy | Gratis, instantáneo, sin cuenta, app Android/iOS/web. Cada alerta trae botón **"Responder en Facebook/LinkedIn…"** que abre la publicación; en X la respuesta llega **pre-escrita** con el opener. Facebook/LinkedIn no permiten pre-llenar mensajes desde un link: mantén presionado el opener en la notificación para copiarlo. |
| **Hosting** | **DigitalOcean VPS + Docker** (primario) | 24/7 real, chequea Freelancer cada 10 min. Droplet de $6/mes → con tus $200 de crédito tienes **más de 2 años**. |
| **Fallback** | GitHub Actions "dormido" | Si la VPS muere, descomentas 2 líneas y sigue funcionando (con menos frecuencia). |

### ¿VPS o GitHub Actions? → **VPS**, con Actions de respaldo
- GitHub Actions: el cron mínimo es 5 min pero en la práctica **se retrasa 10-30 min o más**, a veces se salta corridas,
  y cada corrida arranca de cero (instala deps, etc.). Sirve para "cada 6 horas", no para "agresivo".
- VPS: proceso vivo en loop, intervalos por fuente, SQLite persistente, logs. Es lo correcto para esto.
- Oracle Free ya lo quemaste; DigitalOcean con el GitHub Student Pack ($200) es la mejor opción. Hetzner (€4/mes) sería la alternativa de pago.

---

## 2. Qué necesitas (keys)

| Key | Dónde | Costo |
|---|---|---|
| `NTFY_TOPIC` | Tú lo inventas. Instala la app **ntfy** (Play Store / App Store / https://ntfy.sh/app) → **Subscribe to topic** → escribe el mismo nombre que pongas en el `.env`. El que viene en `.env.example` es `devleads-pe-7x4k9q2m`; **cámbialo por uno propio** (cualquiera que lo adivine vería tus alertas). | Gratis |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey → *Create API key* | Gratis |
| `APIFY_TOKEN` | https://console.apify.com → Settings → *API & Integrations* → *Personal API tokens* | Gratis ($5 créditos/mes) |
| `BRIGHTDATA_API_TOKEN` | https://brightdata.com/cp/setting/users → *API keys* → *Add API key* (se muestra una sola vez). **No** necesitas crear nada en "Acceso web / Agregar API": el bot llama directo al dataset *Facebook - Posts by group URL*. | Gratis (5000 créditos/mes ≈ $5) |
| `TELEGRAM_API_ID/HASH` (opcional) | https://my.telegram.org → API development tools | Gratis |

> Las keys que me pasaste ya las probé y funcionan. Por seguridad **no van dentro del ZIP**: pégalas tú en el `.env`.

---

## 3. Prueba local rápida (2 minutos)

```bash
cd dev-lead-hunter
python3.11 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
nano .env                       # pega GEMINI_API_KEY, APIFY_TOKEN y tu NTFY_TOPIC

python main.py --test-notify    # debe llegar una notificación de ejemplo a tu celular
python main.py --once --force --dry-run --sources freelancer   # prueba sin gastar Apify ni notificar
python main.py --once --force   # pasada real por TODAS las fuentes (gasta ~$0.03 de Apify)
python main.py --stats          # estadísticas, gasto Apify del mes, últimos leads
python main.py                  # modo 24/7 (Ctrl+C para salir)
```

Flags útiles: `--sources freelancer,facebook` (limitar fuentes), `--dry-run` (no notifica), `--force` (ignora intervalos).

---

## 4. Subirlo a GitHub

```bash
cd dev-lead-hunter
git init
git add .
git commit -m "Dev Lead Hunter"
# crea el repo en github.com (privado recomendado) y luego:
git remote add origin https://github.com/TU_USUARIO/dev-lead-hunter.git
git branch -M main
git push -u origin main
```

El `.gitignore` ya excluye `.env`, la base de datos y sesiones. **Nunca subas el `.env`.**

---

## 5. Desplegar en DigitalOcean (24/7)

1. Activa tu crédito: https://education.github.com/pack → DigitalOcean → *Get access* (te da $200 por 1 año).
2. **Create → Droplets**: Región *New York* o *San Francisco* (más cerca de Perú), imagen **Ubuntu 24.04 LTS**,
   plan **Basic → Regular → $6/mes (1 vCPU, 1 GB)**. Autenticación: SSH key (recomendado) o password. Crear.
3. Conéctate: `ssh root@IP_DEL_DROPLET`
4. Instala todo con un comando (reemplaza TU_USUARIO):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/TU_USUARIO/dev-lead-hunter/main/install.sh | bash -s -- https://github.com/TU_USUARIO/dev-lead-hunter.git
   ```
   > Si tu repo es **privado**, primero clónalo a mano con un token: `git clone https://TU_TOKEN@github.com/TU_USUARIO/dev-lead-hunter.git /opt/dev-lead-hunter` y luego `bash /opt/dev-lead-hunter/install.sh`.
5. La primera vez el script crea `/opt/dev-lead-hunter/.env` y se detiene para que lo edites:
   ```bash
   nano /opt/dev-lead-hunter/.env      # pega tus keys, Ctrl+O, Enter, Ctrl+X
   bash /opt/dev-lead-hunter/install.sh
   ```
6. Listo. Te llegará la notificación *"🤖 Dev Lead Hunter iniciado"*.

**Operación diaria**
```bash
cd /opt/dev-lead-hunter
docker compose logs -f                                   # ver en vivo
docker compose exec hunter python main.py --stats        # estadísticas + gasto Apify
docker compose exec hunter python main.py --test-notify  # probar ntfy
docker compose restart                                   # reiniciar
git pull && docker compose up -d --build                 # actualizar código
```
El instalador deja un cron diario que hace `git pull` + rebuild automáticamente si subes cambios al repo.
`restart: unless-stopped` hace que el bot vuelva solo si el droplet se reinicia.

---

## 6. GitHub Actions como motor principal (sin VPS)

`.github/workflows/hunter.yml` corre el bot **cada 20 min** (GitHub puede retrasarlo 5-30 min). En cada corrida el bot
ejecuta solo las fuentes a las que les toca según su intervalo, usando `data/state.json` como memoria (posts ya vistos +
última ejecución de cada fuente), que el propio workflow commitea al repo.

1. Repo → **Settings → Secrets and variables → Actions → Secrets** → `GEMINI_API_KEY`, `APIFY_TOKEN`, `BRIGHTDATA_API_TOKEN`, `NTFY_TOPIC`, `OXION_API_KEY` (solo el valor, sin comillas).
2. **Settings → Actions → General → Workflow permissions → Read and write permissions → Save.**
3. Pestaña **Actions** → si aparece el aviso de habilitar workflows, acéptalo → **dev-lead-hunter → Run workflow** para la primera corrida (ver logs ahí mismo).
4. Después corre solo. Para pausar: **Actions → dev-lead-hunter → ⋯ → Disable workflow**.

Afinar sin tocar código: **Settings → Secrets and variables → Actions → Variables** → ej. `FACEBOOK_GROUPS`,
`LINKEDIN_KEYWORDS`, `MIN_SCORE`, `FACEBOOK_INTERVAL_MINUTES`, `APIFY_MONTHLY_BUDGET_USD`. Los nombres son los mismos del `.env.example`.

> Repos **públicos**: minutos ilimitados. Repos **privados**: 2000 min/mes (3000 con GitHub Pro / Student Pack) → usa `cron: "*/45 * * * *"` o `"0 * * * *"`.
> `data/state.json` solo guarda IDs de posts vistos, última ejecución por fuente y contadores — **no** el texto de los leads — así que un repo público no expone nada útil.
> **Nunca** corras Actions y la VPS a la vez: tendrías dos bots con memorias distintas → leads duplicados y doble gasto de Apify.

---

## 6b. Propuestas automáticas con Claude (Oxion AI) + botón "Copiar"

Para leads de **Freelancer en español**, Claude (vía tu cuenta de Oxion AI, API compatible OpenAI) redacta con **tu prompt**
(`prompts/proposal_es.md`) una propuesta lista para pegar, **cuánto cobrar (USD)**, **en cuántos días**, una justificación y
una pregunta/riesgo para el chat. En inglés y en las demás fuentes no se genera (configurable con `PROPOSAL_SOURCES` / `PROPOSAL_LANGUAGES`).

- **Key**: https://www.oxionai.com → dashboard → API key → `OXION_API_KEY` (Secret en GitHub). Modelo: `OXION_MODEL=claude-sonnet-5`
  (lista los disponibles con `python main.py --models`).
- **Botón "📋 Copiar propuesta"** en la notificación: abre una mini página de tu **GitHub Pages** (color azul = Freelancer, verde =
  Facebook, morado = LinkedIn, negro = X, naranja = Reddit; contenido en negrita) con precio, plazo, la propuesta y botones de copiar.
  Actívalo una vez: repo → **Settings → Pages → Source: Deploy from a branch → Branch `main` → carpeta `/docs` → Save**.
  La carpeta `docs/` (con `index.html`, `.nojekyll` y `p/`) **debe existir en el repo** antes de activar Pages; ya viene en el ZIP.
  Si Pages marca *"No such file or directory - /docs"*, es porque falta esa carpeta: súbela, haz push y vuelve a guardar en Settings → Pages.
  El workflow commitea las páginas en `docs/p/<id>.html`; la URL no se adivina (hash) y lleva `noindex`. La página tarda ~1 min en
  publicarse tras cada corrida.
- Coloca tu experiencia extra en la variable `PROPOSAL_EXPERIENCE` (va en `{{EXPERIENCIA_RELEVANTE}}`). Para cambiar el prompt edita
  `prompts/proposal_es.md` (placeholders: `{{DESCRIPCION}}`, `{{PRESUPUESTO}}`, `{{PROMEDIO}}`, `{{INFO_CLIENTE}}`, `{{EXPERIENCIA_RELEVANTE}}`).
- Si Oxion no responde, el lead igual te llega (con el mensaje sugerido) y una nota de que la propuesta no se generó.

## 6c. Anti-estafa: monedas excluidas

`EXCLUDED_CURRENCIES=INR` (por defecto) descarta proyectos cuyo presupuesto esté en rupias **o** que mencionen INR/₹/rupees en el texto
(se reportaron estafas con ese medio de pago). Agrega más códigos separados por coma si lo necesitas.

## 6d. Grupos de Facebook con Bright Data (cada 6 h)

El bot usa la **Web Scraper API** de Bright Data (dataset `gd_lz11l67o2cb3r0lkj3`, *Facebook - Posts by group URL*) para leer los
grupos de `BRIGHTDATA_GROUPS`. Cómo funciona y cómo cuida tu crédito:

- **Asíncrono**: dispara un *snapshot* con todos los grupos, espera hasta `BRIGHTDATA_WAIT_SECONDS` (7 min) y descarga. Si Bright Data
  tarda más, guarda el `snapshot_id` en `data/state.json` y lo **retoma en la corrida siguiente** (sin disparar ni pagar de nuevo).
- **Solo posts nuevos**: filtra por fecha (`BRIGHTDATA_DAYS_BACK=1` → desde ayer) y envía los IDs ya vistos en `posts_to_not_include`.
- **Tope mensual**: cuenta los registros entregados y deja de disparar al llegar a `BRIGHTDATA_MONTHLY_RECORDS` (3000 ≈ $4.5).
  Con 6 grupos × 4 posts × 4 veces/día ≈ 2900/mes. Para más grupos baja `BRIGHTDATA_POSTS_PER_GROUP` o sube el intervalo.
- **Apify queda para la búsqueda global** por palabra clave (`FACEBOOK_SEARCH_*`) y X. El scraper de grupos de Apify (`FACEBOOK_ENABLED`)
  queda **apagado** para no pagar dos veces por los mismos grupos.
- Si Bright Data no responde o un snapshot falla, te llega un aviso por ntfy (máx. 1 cada 6 h) y el resto de fuentes sigue normal.
- `python main.py --stats` muestra los registros usados en el mes y si hay un snapshot pendiente.
- Prueba sin notificar: `python main.py --once --force --dry-run --sources fbgroups` (gasta ~24 registros ≈ $0.04).

## 7. Costos y presupuesto de Apify (importante)

Precios medidos en el POC: **Facebook ≈ $0.0045 por post leído**, **LinkedIn ≈ $0.0012 por post**, **X gratis** (límite ~50 runs/mes en cuenta free).
Con los valores por defecto del `.env.example`:

| Fuente | Intervalo | Por run | Al mes |
|---|---|---|---|
| Facebook (1 grupo × 5 posts) | 12 h | ~$0.02 | ~$1.4 |
| LinkedIn (2 keywords × 10) | 12 h | ~$0.024 | ~$1.5 |
| X (20 tweets) | 16 h | $0 | $0 (45 runs) |
| Freelancer | 10 min | $0 | $0 |
| **Total** | | | **≈ $3 / mes** (dentro de los $5 gratis) |

El bot consulta el gasto real a la API de Apify antes de cada run y **se detiene solo** al llegar a `APIFY_MONTHLY_BUDGET_USD` (4.5 por defecto).
Si quieres ser más agresivo en Facebook (ej. 5 grupos cada 2 h), sube al plan Starter de Apify ($49/mes) o reduce `FACEBOOK_POSTS_PER_GROUP`.

**Gemini**: free tier ≈ 15 req/min y ~1000/día → el bot respeta `GEMINI_MIN_INTERVAL_SEC=4.5` y `GEMINI_DAILY_LIMIT=900`.
Si se agota, clasifica solo por keywords y lo marca en la notificación.

---

## 8. Afinar el bot

- **Grupos de Facebook** (`BRIGHTDATA_GROUPS`): deben ser **públicos**. Los mejores para leads no son grupos de programadores sino de
  **emprendedores / negocios / tu ciudad** ("Emprendedores Perú", "Negocios Lima", "Compra y venta Arequipa"). Copia la URL del grupo tal cual.
- **Keywords LinkedIn** (`LINKEDIN_KEYWORDS`): frases que diría un cliente: `busco desarrollador`, `necesito un sistema`, `cotización página web`.
  (La búsqueda de LinkedIn vía Apify es la de menor calidad: espera ruido.)
- **Query X** (`TWITTER_QUERY`): sintaxis de búsqueda avanzada de X. Agrega `lang:es` si solo quieres español.
- **Freelancer** (`FREELANCER_QUERIES_ES/EN`): términos de búsqueda; la fuente más productiva y gratis.
- **Sensibilidad**: `MIN_SCORE` (90 = solo leads muy claros). Bájalo a 80-85 si quieres ver más; a 65 para ver casi todo.
- **Prompt de la IA**: `classifier.py` → `SYSTEM_PROMPT`. Ahí defines qué es y qué no es un lead para ti.
- **Keywords** (pre-filtro): `keywords.py` → `NEED_PATTERNS`, `NEGATIVE_PATTERNS`, `SOFTWARE_TERMS`.

---

## 9. Estructura

```
dev-lead-hunter/
├── main.py                 # CLI + loop 24/7 + pipeline
├── config.py               # toda la configuración via .env
├── keywords.py             # pre-filtro ES/EN (barato)
├── classifier.py           # Gemini (JSON estricto) + fallback
├── notifier.py             # ntfy
├── storage.py              # SQLite: dedup, leads, estado, export JSON (Actions)
├── sources/
│   ├── base.py             # Post / Source
│   ├── freelancer.py       # API pública
│   ├── reddit.py           # JSON público (tolerante a 403)
│   ├── brightdata_facebook.py # Bright Data Web Scraper API (grupos de Facebook, asincrono + tope mensual)
│   ├── apify_base.py       # cliente Apify + budget guard real
│   ├── apify_facebook.py   # apify/facebook-groups-scraper
│   ├── apify_linkedin.py   # datadoping/linkedin-posts-search-scraper
│   ├── apify_twitter.py    # simoit/x-twitter-search-tweets-scrapper
│   └── telegram_groups.py  # Telethon (opcional, experimental)
├── test_core.py            # POC: prueba cada integración por separado
├── Dockerfile / docker-compose.yml / install.sh
├── .github/workflows/hunter.yml   # fallback dormido
├── .env.example
└── data/                   # hunter.db, hunter.log (persistente)
```

---

## 10. Preguntas frecuentes

**¿Me pueden banear?** No: el bot nunca inicia sesión en Facebook/LinkedIn/X. Apify lee contenido público con su propia infraestructura.
Lo único que haces tú es escribirle a la persona **manualmente** cuando te llega la alerta (y eso es lo recomendable: un mensaje humano convierte mucho más que uno automático).

**¿Por qué no responde automáticamente?** Responder automáticamente en Facebook/LinkedIn sí requiere tu sesión y es la forma más rápida de que te suspendan la cuenta. El bot te da la alerta en segundos + un *opener* sugerido; tú lo envías en 10 segundos desde tu celular.

**Reddit no trae nada.** Es normal desde una IP de datacenter (403). Si consigues credenciales de app algún día, ponlas en `REDDIT_CLIENT_ID/SECRET` y el bot usará OAuth automáticamente.

**Me llegan muchas alertas / muy pocas.** Ajusta `MIN_SCORE` y los queries de cada fuente. Mira `python main.py --stats`.

**¿Cómo agrego otra fuente?** Crea `sources/mi_fuente.py` heredando de `Source` (o `ApifySource`), implementa `fetch() -> list[Post]` y regístrala en `sources/__init__.py`.
