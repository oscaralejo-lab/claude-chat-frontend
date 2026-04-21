#!/usr/bin/env bash
# install.sh
# ─────────────────────────────────────────────────────────────────────────────
# Instalación completa del Render Server en un servidor Debian/Ubuntu limpio.
#
# Uso (como root):
#   bash install.sh
#
# Variables opcionales (exportar antes de ejecutar):
#   RENDER_BEARER_TOKEN   Token de autorización (déjalo vacío para acceso abierto)
#   RENDER_PORT           Puerto del servidor (por defecto: 5001)
#   RENDER_PUBLIC_URL     URL pública del servidor (ej: https://miservidor.com)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/oscaralejo-lab/claude-chat-frontend/copilot/create-render-server-directory"
INSTALL_DIR="/opt/news_radio_24_7/render_server"
OUTPUT_DIR="/opt/news_radio_24_7/render_output"
VENDOR_DIR="/opt/news_radio_24_7/web/vendor/live2d"
MODEL_DIR="/opt/news_radio_24_7/web/live2d"
SERVICE="news-radio-render"
SERVICE_FILE="/etc/systemd/system/${SERVICE}.service"
RENDER_PORT="${RENDER_PORT:-5001}"
RENDER_PUBLIC_URL="${RENDER_PUBLIC_URL:-http://127.0.0.1:${RENDER_PORT}}"
RENDER_BEARER_TOKEN="${RENDER_BEARER_TOKEN:-}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

[[ "${EUID}" -eq 0 ]] || fail "Este script debe ejecutarse como root."

# ── 1. Crear directorios ──────────────────────────────────────────────────────
info "Creando directorios..."
mkdir -p "${INSTALL_DIR}" "${OUTPUT_DIR}" "${VENDOR_DIR}" "${MODEL_DIR}"
ok "Directorios listos"

# ── 2. Instalar dependencias del sistema ──────────────────────────────────────
info "Actualizando repositorios e instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    xvfb \
    ffmpeg \
    curl \
    ca-certificates
ok "Dependencias del sistema instaladas"

# ── 3. Instalar dependencias Python ──────────────────────────────────────────
info "Instalando Flask y Playwright..."
pip3 install --quiet --break-system-packages flask>=3.0 playwright>=1.44 2>/dev/null \
  || pip3 install --quiet flask>=3.0 playwright>=1.44
ok "Paquetes Python instalados"

# ── 4. Instalar navegador Playwright (Chromium) ───────────────────────────────
info "Instalando Chromium para Playwright (puede tardar varios minutos)..."
python3 -m playwright install chromium
python3 -m playwright install-deps chromium
ok "Chromium instalado"

# ── 5. Descargar archivos del servidor desde GitHub ───────────────────────────
info "Descargando render_server.py..."
curl --fail --location --silent --show-error --max-time 30 \
     "${REPO_RAW}/render_server/render_server.py" \
     -o "${INSTALL_DIR}/render_server.py"
ok "render_server.py descargado"

info "Descargando capture.html..."
curl --fail --location --silent --show-error --max-time 30 \
     "${REPO_RAW}/render_server/capture.html" \
     -o "${INSTALL_DIR}/capture.html"
ok "capture.html descargado"

info "Descargando deploy_and_test.sh..."
curl --fail --location --silent --show-error --max-time 30 \
     "${REPO_RAW}/render_server/deploy_and_test.sh" \
     -o "${INSTALL_DIR}/deploy_and_test.sh"
chmod +x "${INSTALL_DIR}/deploy_and_test.sh"
ok "deploy_and_test.sh descargado"

# ── 6. Instalar el servicio systemd ──────────────────────────────────────────
info "Instalando servicio systemd ${SERVICE}..."
cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=News Radio 24/7 – Render Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/render_server.py
Restart=always
RestartSec=5
Environment=RENDER_HOST=0.0.0.0
Environment=RENDER_PORT=${RENDER_PORT}
Environment=RENDER_PUBLIC_URL=${RENDER_PUBLIC_URL}
Environment=RENDER_OUTPUT_DIR=${OUTPUT_DIR}
Environment=LIVE2D_VENDOR_DIR=${VENDOR_DIR}
Environment=LIVE2D_MODEL_DIR=${MODEL_DIR}
EOF

if [[ -n "${RENDER_BEARER_TOKEN}" ]]; then
  echo "Environment=RENDER_BEARER_TOKEN=${RENDER_BEARER_TOKEN}" >> "${SERVICE_FILE}"
fi

cat >> "${SERVICE_FILE}" << 'EOF'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
ok "Servicio ${SERVICE} instalado y arrancado"

# ── 7. Verificar que el servidor responde ─────────────────────────────────────
info "Esperando que el servidor esté activo (máx. 30 s)..."
MAX=30; WAITED=0
until curl --silent --fail --max-time 2 "http://127.0.0.1:${RENDER_PORT}/health" >/dev/null 2>&1; do
  sleep 1; WAITED=$((WAITED + 1))
  [[ ${WAITED} -ge ${MAX} ]] && fail "El servidor no respondió en ${MAX} s.
Revisa los logs: journalctl -u ${SERVICE} -n 50 --no-pager"
  printf "."
done
echo ""
ok "Servidor activo en http://127.0.0.1:${RENDER_PORT}"

# ── Listo ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  RENDER SERVER INSTALADO Y FUNCIONANDO CORRECTAMENTE${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Puerto:         ${RENDER_PORT}"
echo "  URL pública:    ${RENDER_PUBLIC_URL}"
echo "  Directorio:     ${INSTALL_DIR}"
echo "  Videos:         ${OUTPUT_DIR}"
echo "  Logs:           journalctl -u ${SERVICE} -f"
echo ""
echo "  Para colocar el modelo Live2D (opcional):"
echo "    rsync -av miara/  ${MODEL_DIR}/miara/"
echo ""
echo "  Para ejecutar el smoke-test:"
echo "    bash ${INSTALL_DIR}/deploy_and_test.sh"
echo ""
