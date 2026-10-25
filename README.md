# Dev Lead Hunter 🎯

Bot "agresivo" que vigila redes sociales y portales 24/7 buscando **personas o negocios que NECESITAN un ingeniero de
software / sistemas** (no ofertas de empleo corporativo, no gente ofreciendo servicios) y te avisa **al instante en tu
celular por ntfy** con: resumen, score 0-100, link directo a la publicación y una frase sugerida para abrir conversación.

```
Fuentes ──► Dedup (SQLite) ──► Filtro keywords ES/EN ──► Gemini (IA) ──► ntfy 📲
 Facebook grupos (Apify)      barato, 0 costo       is_lead / score / resumen / opener
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
| **Facebook / LinkedIn / X** | **Apify** (scraping como servicio) | **No usa tus credenciales → cero riesgo de que te baneen tu cuenta.** Solo lee grupos/posts PÚBLICOS. Plan gratis: $5 de créditos/mes. |
| **Freelancer.com** | API pública, sin key | Gratis e ilimitada. Todo lo que publica un cliente ahí es un pedido real de trabajo. Soporta español. |
| **Reddit** | JSON público, tolerante | Reddit cerró la creación self-service de apps (nov 2025) y bloquea IPs cloud. El bot lo intenta; si responde 403 lo pausa 6 h y sigue con el resto. **No rompe nada.** |
| **Nitter (X gratis)** | Descartado | En 2026 ya no quedan instancias funcionales. X solo por Apify. |
| **Workana / Upwork** | Descartados por ahora | Están detrás de Cloudflare. Se pueden agregar vía Apify si lo necesitas. |
| **IA** | Gemini `gemini-3.5-flash-lite` (gratis) | ~1000 clasificaciones/día gratis. Salida JSON estricta. Si se acaba la cuota → fallback automático a keywords. |
| **Notificaciones** | ntfy | Gratis, instantáneo, sin cuenta, app Android/iOS/web. |
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

## 6. Fallback: GitHub Actions "dormido"

El archivo `.github/workflows/hunter.yml` **no se ejecuta solo**. Si algún día pierdes la VPS:

1. Repo → **Settings → Secrets and variables → Actions** → agrega `GEMINI_API_KEY`, `APIFY_TOKEN`, `NTFY_TOPIC`.
2. **Settings → Actions → General → Workflow permissions → Read and write** (para que guarde `data/state.json`, el archivo de "ya vistos").
3. Edita `hunter.yml` y descomenta:
   ```yaml
   schedule:
     - cron: "*/30 * * * *"
   ```
4. Commit. También puedes lanzarlo a mano: pestaña **Actions → dev-lead-hunter (fallback) → Run workflow**.

En Actions el bot corre con `--once --force` (todas las fuentes cada corrida). Por defecto el workflow deja
LinkedIn y X desactivados ahí para cuidar el presupuesto de Apify; actívalos con *Variables* del repo (`LINKEDIN_ENABLED=true`, etc.).

---

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

- **Grupos de Facebook** (`FACEBOOK_GROUPS`): deben ser **públicos**. Los mejores para leads no son grupos de programadores sino de
  **emprendedores / negocios / tu ciudad** ("Emprendedores Perú", "Negocios Lima", "Compra y venta Arequipa"). Copia la URL del grupo tal cual.
- **Keywords LinkedIn** (`LINKEDIN_KEYWORDS`): frases que diría un cliente: `busco desarrollador`, `necesito un sistema`, `cotización página web`.
  (La búsqueda de LinkedIn vía Apify es la de menor calidad: espera ruido.)
- **Query X** (`TWITTER_QUERY`): sintaxis de búsqueda avanzada de X. Agrega `lang:es` si solo quieres español.
- **Freelancer** (`FREELANCER_QUERIES_ES/EN`): términos de búsqueda; la fuente más productiva y gratis.
- **Sensibilidad**: `MIN_SCORE` (65). Súbelo a 75 si llegan muchos leads flojos; bájalo a 55 si quieres ver todo.
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
