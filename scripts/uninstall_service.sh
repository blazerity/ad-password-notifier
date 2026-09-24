#!/usr/bin/env bash
# Удаление systemd-службы AD Password Notifier.
# Каталог приложения и данные не удаляются.
set -euo pipefail

SERVICE_NAME="ad-password-notifier"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Запустите от root: sudo $0" >&2
  exit 1
fi

systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl reset-failed "${SERVICE_NAME}.service" 2>/dev/null || true

echo "Служба ${SERVICE_NAME} удалена."
echo "Каталог приложения и пользователь ad-pwd-notifier сохранены."
