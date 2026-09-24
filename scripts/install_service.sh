#!/usr/bin/env bash
# Установка systemd-службы из уже развёрнутого каталога приложения.
# Запускать от root: sudo ./scripts/install_service.sh
set -euo pipefail

SERVICE_NAME="ad-password-notifier"
SERVICE_USER="ad-pwd-notifier"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SRC="${SCRIPT_DIR}/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON="${APP_DIR}/.venv/bin/python"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Запустите от root: sudo $0" >&2
  exit 1
fi

if [[ ! -x "${PYTHON}" ]]; then
  echo "[ERROR] Не найден ${PYTHON}" >&2
  echo "Создайте venv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "[ERROR] Не найден unit-файл ${UNIT_SRC}" >&2
  exit 1
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
  echo "[OK] Создан системный пользователь ${SERVICE_USER}"
fi

mkdir -p "${APP_DIR}/logs" "${APP_DIR}/data" "${APP_DIR}/data/previews"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
if [[ -f "${APP_DIR}/.env" ]]; then
  chmod 600 "${APP_DIR}/.env"
fi
if [[ -f "${APP_DIR}/config.ini" ]]; then
  chmod 640 "${APP_DIR}/config.ini"
fi

# Подставить фактический APP_DIR в unit (по умолчанию /opt/...)
TMP_UNIT="$(mktemp)"
sed \
  -e "s|/opt/ad-password-notifier|${APP_DIR}|g" \
  "${UNIT_SRC}" > "${TMP_UNIT}"
install -m 644 "${TMP_UNIT}" "${UNIT_DST}"
rm -f "${TMP_UNIT}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo
echo "Служба ${SERVICE_NAME} установлена (enable)."
echo "Перед первым стартом заполните config.ini и .env, затем:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "Web UI по умолчанию: http://127.0.0.1:8787/"
