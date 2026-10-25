#!/usr/bin/env bash
# ------------------------------------------------------------------
#  Dev Lead Hunter - instalador para DigitalOcean / Ubuntu 22.04-24.04
#  Uso (en el droplet, como root):
#     curl -fsSL https://raw.githubusercontent.com/TU_USUARIO/dev-lead-hunter/main/install.sh | bash -s -- https://github.com/TU_USUARIO/dev-lead-hunter.git
#  o si ya clonaste el repo:   bash install.sh
# ------------------------------------------------------------------
set -euo pipefail

REPO_URL="${1:-}"
APP_DIR="${APP_DIR:-/opt/dev-lead-hunter}"

echo "==> [1/5] Paquetes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y >/dev/null
apt-get install -y ca-certificates curl git ufw >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  echo "==> [2/5] Instalando Docker"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  echo "==> [2/5] Docker ya instalado"
fi

echo "==> [3/5] Codigo"
if [ -n "$REPO_URL" ]; then
  if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
  else
    git clone "$REPO_URL" "$APP_DIR"
  fi
else
  # ejecutado desde dentro del repo ya clonado
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
cd "$APP_DIR"
mkdir -p data

echo "==> [4/5] Configuracion"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "  >>> Se creo $APP_DIR/.env a partir de .env.example"
  echo "  >>> EDITALO AHORA con tus keys:   nano $APP_DIR/.env"
  echo "  >>> (GEMINI_API_KEY, APIFY_TOKEN, NTFY_TOPIC) y luego vuelve a correr:  bash install.sh"
  echo ""
  exit 0
fi

# Firewall basico (solo SSH). El bot no abre puertos.
ufw --force enable >/dev/null 2>&1 || true
ufw allow OpenSSH >/dev/null 2>&1 || true

echo "==> [5/5] Levantando el bot (docker compose)"
docker compose up -d --build

# Auto-actualizacion opcional: cron diario que hace git pull + rebuild si hay cambios
cat >/etc/cron.daily/dev-lead-hunter-update <<EOF
#!/usr/bin/env bash
cd $APP_DIR && git fetch -q && if [ "\$(git rev-parse HEAD)" != "\$(git rev-parse @{u})" ]; then git pull -q --ff-only && docker compose up -d --build; fi
EOF
chmod +x /etc/cron.daily/dev-lead-hunter-update

echo ""
echo "============================================================"
echo "  Dev Lead Hunter corriendo 24/7"
echo "  Logs en vivo:      cd $APP_DIR && docker compose logs -f"
echo "  Estadisticas:      docker compose exec hunter python main.py --stats"
echo "  Probar ntfy:       docker compose exec hunter python main.py --test-notify"
echo "  Reiniciar:         docker compose restart"
echo "  Actualizar codigo: git pull && docker compose up -d --build"
echo "============================================================"
