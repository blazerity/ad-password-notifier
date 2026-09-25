#!/usr/bin/env bash
# Онлайн-установка AD Password Notifier на Debian 12 из git.
#
# Одной строкой (после публикации репозитория / ветки):
#   curl -fsSL https://raw.githubusercontent.com/blazerity/ad-password-notifier/main/scripts/install_debian.sh | sudo bash
#
# Параметры окружения (необязательно):
#   REPO_URL=https://github.com/blazerity/ad-password-notifier.git
#   BRANCH=main
#   INSTALL_DIR=/opt/ad-password-notifier
#   SKIP_SERVICE=1          — не ставить systemd
#   START_SERVICE=1         — сразу systemctl start (только если конфиг уже готов)
#
# Или из уже склонированного репозитория:
#   sudo ./scripts/install_debian.sh --local
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/blazerity/ad-password-notifier.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/ad-password-notifier}"
SERVICE_USER="ad-pwd-notifier"
SKIP_SERVICE="${SKIP_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"
LOCAL_MODE=0

usage() {
  cat <<'EOF'
Usage: install_debian.sh [--local] [--branch NAME] [--dir PATH] [--repo URL]
                         [--skip-service] [--start]

  --local          установить из текущего checkout (не клонировать)
  --branch NAME    ветка git (по умолчанию main)
  --dir PATH       каталог установки (по умолчанию /opt/ad-password-notifier)
  --repo URL       URL репозитория
  --skip-service   не устанавливать systemd-службу
  --start          сразу запустить службу после установки
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) LOCAL_MODE=1; shift ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --skip-service) SKIP_SERVICE=1; shift ;;
    --start) START_SERVICE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Запустите от root (sudo)." >&2
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "[ERROR] Не удалось определить ОС (/etc/os-release)." >&2
  exit 1
fi
# shellcheck source=/dev/null
. /etc/os-release
if [[ "${ID:-}" != "debian" ]]; then
  echo "[WARN] Ожидался Debian, сейчас ID=${ID:-unknown}. Продолжаем..."
fi
if [[ "${VERSION_ID:-}" != "12" ]]; then
  echo "[WARN] Целевая платформа — Debian 12, сейчас VERSION_ID=${VERSION_ID:-unknown}."
fi

export DEBIAN_FRONTEND=noninteractive
echo "[1/6] Пакеты: git, python3, venv, pip, build-essential..."
apt-get update -qq
apt-get install -y -qq \
  git \
  ca-certificates \
  curl \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  libffi-dev

PYTHON_BIN="$(command -v python3)"
PY_VER="$("${PYTHON_BIN}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "[OK] Python ${PY_VER} (${PYTHON_BIN})"
# 3.11 на Debian 12; допускаем 3.11+
"${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "[ERROR] Нужен Python 3.11+, сейчас ${PY_VER}" >&2; exit 1; }

if [[ "${LOCAL_MODE}" -eq 1 ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  echo "[2/6] Локальный режим: копирование из ${SRC_DIR} → ${INSTALL_DIR}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  if [[ "${SRC_DIR}" != "${INSTALL_DIR}" ]]; then
    mkdir -p "${INSTALL_DIR}"
    tar -C "${SRC_DIR}" \
      --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
      --exclude='config.ini' --exclude='.env' \
      -cf - . | tar -C "${INSTALL_DIR}" -xf -
  else
    echo "[OK] Установка в текущий каталог ${INSTALL_DIR}"
  fi
else
  echo "[2/6] Клонирование ${REPO_URL} (ветка ${BRANCH}) → ${INSTALL_DIR}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    git -C "${INSTALL_DIR}" fetch --depth 1 origin "${BRANCH}"
    git -C "${INSTALL_DIR}" checkout -B "${BRANCH}" "FETCH_HEAD"
  else
    rm -rf "${INSTALL_DIR}"
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  fi
fi

cd "${INSTALL_DIR}"

echo "[3/6] Виртуальное окружение и зависимости..."
if [[ ! -d .venv ]]; then
  "${PYTHON_BIN}" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q
.venv/bin/python -c "import fastapi, ldap3, apscheduler; print('[OK] imports')"

echo "[4/6] Конфигурация (примеры, если ещё нет)..."
if [[ ! -f config.ini ]]; then
  cp config.example.ini config.ini
  echo "[OK] Создан config.ini из примера — отредактируйте перед боевым запуском"
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[OK] Создан .env из примера — задайте пароли"
fi
mkdir -p logs data data/previews
chmod 750 data logs
chmod 640 config.ini 2>/dev/null || true
chmod 600 .env 2>/dev/null || true

echo "[5/6] Права и исполняемые скрипты..."
chmod +x "${INSTALL_DIR}/scripts/"*.sh

if [[ "${SKIP_SERVICE}" -eq 0 ]]; then
  echo "[6/6] systemd-служба..."
  bash "${INSTALL_DIR}/scripts/install_service.sh"
  if [[ "${START_SERVICE}" -eq 1 ]]; then
    systemctl start ad-password-notifier
    systemctl --no-pager --full status ad-password-notifier || true
  fi
else
  echo "[6/6] Пропуск systemd (SKIP_SERVICE=1)"
  if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
  fi
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
  chmod 600 "${INSTALL_DIR}/.env"
  chmod 640 "${INSTALL_DIR}/config.ini"
fi

cat <<EOF

========================================
AD Password Notifier установлен.
Каталог: ${INSTALL_DIR}
Ветка:   ${BRANCH}

Дальше:
  1. sudo nano ${INSTALL_DIR}/config.ini
  2. sudo nano ${INSTALL_DIR}/.env
  3. sudo -u ${SERVICE_USER} ${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/main.py --dry-run
  4. sudo systemctl enable --now ad-password-notifier
  5. Откройте http://127.0.0.1:8787/

Документация: ${INSTALL_DIR}/DEPLOYMENT.md
========================================
EOF
