#!/usr/bin/env bash
# deploy_and_test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Uso en el servidor Contabo (como root):
#
#   cd /opt/news_radio_24_7
#   bash render_server/deploy_and_test.sh
#
# Qué hace:
#   1. Descarga el render_server.py correcto desde GitHub
#   2. Reinicia el servicio systemd
#   3. Espera a que el servidor esté activo (hasta 30 s)
#   4. Genera un MP3 de prueba de 5 segundos (tono 440 Hz)
#   5. Llama al endpoint /render y descarga el MP4 resultante
#   6. Verifica que el MP4 existe y pesa > 100 KB → ÉXITO / FALLA
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuración ─────────────────────────────────────────────────────────────
REPO_RAW="https://raw.githubusercontent.com/oscaralejo-lab/claude-chat-frontend/copilot/create-render-server-directory"
RENDER_PORT="${RENDER_PORT:-5001}"
BASE_URL="http://127.0.0.1:${RENDER_PORT}"
SERVICE="news-radio-render"
INSTALL_DIR="/opt/news_radio_24_7/render_server"
TOKEN="${RENDER_BEARER_TOKEN:-}"          # Si el servicio requiere token, expórtalo antes

TITLE="Prueba automática del render server"
SUBTITLE="Verificación de video con audio y lower-third"
TEST_OUT="/tmp/render_test_$(date +%s).mp4"

# ── Colores ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

# ── 1. Restaurar render_server.py ─────────────────────────────────────────────
info "Descargando render_server.py desde GitHub..."
curl --fail --location --silent --show-error --max-time 30 \
     "${REPO_RAW}/render_server/render_server.py" \
     -o "${INSTALL_DIR}/render_server.py"
ok "render_server.py restaurado"

# ── 2. Reiniciar servicio ─────────────────────────────────────────────────────
info "Reiniciando ${SERVICE}..."
systemctl restart "${SERVICE}"

# ── 3. Esperar a que el servidor responda ─────────────────────────────────────
info "Esperando que el servidor esté activo (máx. 30 s)..."
MAX=30; WAITED=0
until curl --silent --fail --max-time 2 "${BASE_URL}/health" >/dev/null 2>&1; do
  sleep 1; WAITED=$((WAITED + 1))
  if [[ ${WAITED} -ge ${MAX} ]]; then
    echo ""
    fail "El servidor no respondió en ${MAX} s. Revisa: journalctl -u ${SERVICE} -n 30 --no-pager"
  fi
  printf "."
done
echo ""
ok "Servidor activo en ${BASE_URL}"

# ── 4. Generar MP3 de prueba (5 s, tono 440 Hz) ───────────────────────────────
TEST_MP3=$(mktemp /tmp/render_test_XXXXXX.mp3)
info "Generando MP3 de prueba (5 s, tono 440 Hz)..."
ffmpeg -y -f lavfi -i "sine=frequency=440:duration=5" \
       -codec:a libmp3lame -q:a 4 "${TEST_MP3}" \
       -loglevel error
ok "MP3 generado: ${TEST_MP3}"

# ── 5. Llamar al endpoint /render ─────────────────────────────────────────────
info "Enviando solicitud de render..."
CURL_AUTH=()
if [[ -n "${TOKEN}" ]]; then
  CURL_AUTH=(-H "Authorization: Bearer ${TOKEN}")
fi

RESPONSE=$(
  curl --fail --silent --max-time 180 \
    "${CURL_AUTH[@]}" \
    -F "audio=@${TEST_MP3};type=audio/mpeg" \
    -F "title=${TITLE}" \
    -F "subtitle=${SUBTITLE}" \
    "${BASE_URL}/render"
)

VIDEO_URL=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('videoUrl',''))" 2>/dev/null || true)

if [[ -z "${VIDEO_URL}" ]]; then
  fail "El servidor no devolvió videoUrl. Respuesta: ${RESPONSE}"
fi
ok "Video generado: ${VIDEO_URL}"

# ── 6. Descargar y verificar el MP4 ──────────────────────────────────────────
info "Descargando MP4..."
curl --fail --silent --max-time 60 "${VIDEO_URL}" -o "${TEST_OUT}"

SIZE=$(stat -c%s "${TEST_OUT}" 2>/dev/null || echo 0)
if [[ ${SIZE} -lt 102400 ]]; then   # < 100 KB → sospechoso
  fail "El MP4 existe pero es demasiado pequeño (${SIZE} bytes). Puede estar corrupto."
fi

ok "MP4 descargado: ${TEST_OUT}  (${SIZE} bytes)"

# ── Limpieza ──────────────────────────────────────────────────────────────────
rm -f "${TEST_MP3}"

echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  RENDER SERVER FUNCIONANDO CORRECTAMENTE${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo "  Video de prueba guardado en: ${TEST_OUT}"
echo "  Puedes reproducirlo con:     ffplay ${TEST_OUT}"
echo ""
