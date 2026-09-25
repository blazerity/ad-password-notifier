# Развёртывание на Debian 12

Пошаговая инструкция для **Debian 12 (bookworm)**.  
Цель: служба **AD Password Notifier** (systemd) с web UI и ежедневной проверкой паролей AD.

Рекомендуемый путь установки: `/opt/ad-password-notifier`.

---

## Быстрая установка (one-line из git)

На чистом Debian 12 от root:

```bash
curl -fsSL https://raw.githubusercontent.com/blazerity/ad-password-notifier/main/scripts/install_debian.sh | sudo bash
```

Скрипт:

1. ставит `git`, Python 3.11+, `python3-venv`;
2. клонирует ветку в `/opt/ad-password-notifier`;
3. создаёт `.venv` и ставит зависимости;
4. копирует `config.example.ini` → `config.ini` и `.env.example` → `.env` (если их ещё нет);
5. создаёт пользователя `ad-pwd-notifier` и unit `ad-password-notifier.service`.

После установки **обязательно** отредактируйте конфиг и запустите службу (см. ниже).

Параметры (через окружение или аргументы скрипта):

| Переменная / флаг | Значение по умолчанию | Назначение |
|---|---|---|
| `REPO_URL` / `--repo` | `https://github.com/blazerity/ad-password-notifier.git` | репозиторий |
| `BRANCH` / `--branch` | `main` | ветка |
| `INSTALL_DIR` / `--dir` | `/opt/ad-password-notifier` | каталог |
| `SKIP_SERVICE=1` / `--skip-service` | выкл. | не ставить systemd |
| `START_SERVICE=1` / `--start` | выкл. | сразу `systemctl start` |

Пример с другой веткой и автозапуском:

```bash
curl -fsSL https://raw.githubusercontent.com/blazerity/ad-password-notifier/main/scripts/install_debian.sh \
  | sudo env BRANCH=main START_SERVICE=0 bash -s -- --branch main
```

Если репозиторий **приватный**, `curl` к `raw.githubusercontent.com` без токена не сработает.  
Сделайте репозиторий публичным **или** клонируйте вручную (вариант A ниже) и запустите:

```bash
sudo ./scripts/install_debian.sh --local
```

---

## 1. Что понадобится

| Компонент | Зачем |
|---|---|
| Debian **12** (bookworm), amd64 | целевая ОС |
| Python **3.11+** (из репозиториев Debian) | runtime |
| git | клонирование |
| systemd | служба |
| Учётка AD только на **чтение** | LDAP |
| SMTP-релей | письма |
| root / sudo | установка пакетов и unit |

Docker не обязателен.

---

## 2. Сервисная учётка AD

1. Создайте пользователя, например `DOMAIN\svc_pwd_notifier`.
2. **Не** добавляйте в Domain Admins.
3. На нужных OU — чтение списка объектов и свойств user.
4. Пароль только в `.env` (`AD_SERVICE_PASSWORD`).

С Debian-сервера проверьте доступность DC:

```bash
getent hosts dc01.domain.local
# при необходимости: apt install ldap-utils && ldapsearch -x -H ldap://dc01.domain.local -b '' -s base
```

---

## 3. Вариант A — ручная установка из git

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip python3-dev build-essential

sudo mkdir -p /opt
sudo git clone --branch main \
  https://github.com/blazerity/ad-password-notifier.git \
  /opt/ad-password-notifier
cd /opt/ad-password-notifier

sudo python3 -m venv .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -r requirements.txt

sudo cp -n config.example.ini config.ini
sudo cp -n .env.example .env
```

Проверка импортов:

```bash
sudo .venv/bin/python -c "import fastapi, ldap3, apscheduler; print('OK')"
```

---

## 4. Конфигурация

```bash
sudo nano /opt/ad-password-notifier/config.ini
sudo nano /opt/ad-password-notifier/.env
```

### 4.1. `config.ini` — минимум

```ini
[ad]
server = ldap://dc01.domain.local
domain = DOMAIN
service_user = svc_pwd_notifier
search_base = OU=Users,DC=domain,DC=local
excluded_ou =
max_pwd_age_days = 180

[notification]
first_warning_days = 5
daily_warning_threshold = 3
history_csv = data/notification_history.csv
instructions_url = https://intranet.domain.local/howto-change-password

[smtp]
host = mail.domain.local
port = 25
use_tls = false
use_starttls = false
from_address = noreply@domain.local

[admins]
recipients = admin1@domain.local, admin2@domain.local

[schedule]
enabled = true
cron = 0 8 * * *
pause_user_mail_until =

[web]
host = 127.0.0.1
port = 8787
```

Замечания:

- LDAPS: `server = ldaps://dc01.domain.local`.
- `cron` — 5 полей (`минута час день месяц день_недели`).
- `host = 127.0.0.1` — UI только локально. Для LAN: `0.0.0.0` + firewall + **обязательно** `WEB_PASSWORD`.

### 4.2. `.env` — секреты

```env
AD_SERVICE_PASSWORD=********
WEB_USER=admin
WEB_PASSWORD=********

# Необязательно:
# SMTP_USER=noreply@domain.local
# SMTP_PASSWORD=********
```

```bash
sudo chmod 600 /opt/ad-password-notifier/.env
sudo chmod 640 /opt/ad-password-notifier/config.ini
```

---

## 5. Проверка до установки службы

```bash
cd /opt/ad-password-notifier
sudo -u ad-pwd-notifier .venv/bin/python main.py --dry-run
```

Если пользователь службы ещё не создан:

```bash
sudo .venv/bin/python main.py --dry-run
```

Ожидаемо: подключение к AD, превью в `data/previews/`, без SMTP и без записи CSV.

Боевой разовый прогон:

```bash
sudo -u ad-pwd-notifier .venv/bin/python main.py --send
```

Ручной UI без systemd:

```bash
sudo -u ad-pwd-notifier .venv/bin/python main.py --serve
```

Откройте http://127.0.0.1:8787/ (логин/пароль из `.env`). Остановка: `Ctrl+C`.

---

## 6. Установка как systemd-службы

Если ставили one-line или `install_debian.sh` — unit уже зарегистрирован. Иначе:

```bash
cd /opt/ad-password-notifier
sudo ./scripts/install_service.sh
sudo systemctl start ad-password-notifier
sudo systemctl status ad-password-notifier
```

Управление:

```bash
sudo systemctl stop ad-password-notifier
sudo systemctl restart ad-password-notifier
sudo journalctl -u ad-password-notifier -f
```

Логи приложения: `/opt/ad-password-notifier/logs/`.

### Firewall (UI с других хостов)

Только после `host = 0.0.0.0` и сильного `WEB_PASSWORD`:

```bash
# nftables / iptables — по политике сайта; пример для ufw:
sudo apt install -y ufw
sudo ufw allow 8787/tcp
sudo ufw reload
```

---

## 7. Web UI

| Страница | Назначение |
|---|---|
| **Отчёт** | состояние учёток, «Запустить сейчас», тестовый прогон, пауза, ручные напоминания |
| **Настройки** | AD / SMTP / пороги / cron / web; «Проверить соединение и доступ к AD» (по полям формы) / «Проверить SMTP» |

Смена `host` / `port` web требует `systemctl restart ad-password-notifier`.

---

## 8. Обновление версии

```bash
sudo systemctl stop ad-password-notifier
cd /opt/ad-password-notifier
sudo -u ad-pwd-notifier git pull
sudo -u ad-pwd-notifier .venv/bin/pip install -r requirements.txt
sudo systemctl start ad-password-notifier
```

`config.ini`, `.env`, `data/notification_history.csv` в git не коммитьте.

Если one-line ставил от root и владельцы сбились:

```bash
sudo chown -R ad-pwd-notifier:ad-pwd-notifier /opt/ad-password-notifier
```

---

## 9. Удаление службы

```bash
cd /opt/ad-password-notifier
sudo ./scripts/uninstall_service.sh
```

Каталог `/opt/ad-password-notifier` и пользователь `ad-pwd-notifier` остаются.

Полное удаление:

```bash
sudo ./scripts/uninstall_service.sh
sudo userdel ad-pwd-notifier
sudo rm -rf /opt/ad-password-notifier
```

---

## 10. Альтернатива без службы (cron)

Только ежедневная рассылка без web UI:

```bash
sudo crontab -u ad-pwd-notifier -e
```

```cron
0 8 * * * cd /opt/ad-password-notifier && /opt/ad-password-notifier/.venv/bin/python main.py --send >> /opt/ad-password-notifier/logs/cron.log 2>&1
```

Не включайте одновременно cron на `--send` и systemd с `[schedule] enabled = true`.

---

## 11. Диагностика

| Симптом | Куда смотреть |
|---|---|
| Служба не стартует | `journalctl -u ad-password-notifier -xe`, `logs/` |
| Нет LDAP | `[ad]`, `.env`, сеть/DNS до DC, LDAPS/сертификаты |
| Нет писем | `[smtp]`, `SMTP_USER`/`SMTP_PASSWORD`, relay |
| UI 401 | `WEB_PASSWORD` в `.env` |
| UI с другого ПК | `[web] host`, firewall, порт 8787 |
| Permission denied | `chown -R ad-pwd-notifier:ad-pwd-notifier /opt/ad-password-notifier` |

Коды выхода прогона: `0` — ок, `1` — ошибка конфига/AD/SMTP, `2` — уже идёт другой прогон.

---

## 12. Чеклист готовности

- [ ] Debian 12, Python 3.11+
- [ ] Код в `/opt/ad-password-notifier`, `.venv`, зависимости
- [ ] Заполнены `config.ini` и `.env`
- [ ] `--dry-run` успешен
- [ ] `systemctl is-enabled ad-password-notifier` → enabled
- [ ] `systemctl is-active ad-password-notifier` → active
- [ ] UI открывается, Basic Auth работает
- [ ] В UI проверка соединения/доступа AD и SMTP — OK
- [ ] В `[schedule]` нужный cron, `enabled = true`
- [ ] Получатели в `[admins]` корректны
