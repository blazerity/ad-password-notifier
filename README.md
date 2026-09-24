# Уведомления об истечении паролей AD

Приложение на Python 3.11+ для **Windows Server** и **Debian 12**: проверка срока паролей в локальном Active Directory, HTML-письма пользователям, сводный отчёт администраторам и лёгкий web-интерфейс.

Может работать как консольный скрипт (Планировщик заданий / cron) или как **служба** (Windows NSSM / systemd) с встроенным планировщиком и UI. Политики Fine-Grained Password Policies **не учитываются**: используется единый `max_pwd_age_days` из `config.ini`.

**Развёртывание:**

- Windows Server — [DEPLOYMENT.md](DEPLOYMENT.md)
- Debian 12 — [DEPLOYMENT_DEBIAN.md](DEPLOYMENT_DEBIAN.md)

## Возможности

- Выборка активных пользователей по LDAP (`ldap3` + NTLM).
- Расчёт даты истечения: `pwdLastSet + max_pwd_age_days`.
- Первое письмо при пороге 5 дней, ежедневные — с 3 дней и при просрочке.
- История в CSV, чтобы не дублировать письма и фиксировать смену пароля.
- Сводный HTML-отчёт: истекает скоро / просрочено / пароль сменили.
- Web UI: дашборд, настройки INI, расписание, пауза рассылки, ручное напоминание выбранным.
- Режим службы: один процесс = HTTP + APScheduler (NSSM на Windows, systemd на Debian).

## Быстрый старт: Debian 12 (one-line)

На сервере с Debian 12:

```bash
curl -fsSL https://raw.githubusercontent.com/blazerity/ad-password-notifier/cursor/debian-12-deployment-f1d7/scripts/install_debian.sh | sudo bash
```

Затем отредактируйте `/opt/ad-password-notifier/config.ini` и `.env`, проверьте и запустите:

```bash
sudo -u ad-pwd-notifier /opt/ad-password-notifier/.venv/bin/python /opt/ad-password-notifier/main.py --dry-run
sudo systemctl enable --now ad-password-notifier
```

Web UI: http://127.0.0.1:8787/  
Подробности и ручная установка — [DEPLOYMENT_DEBIAN.md](DEPLOYMENT_DEBIAN.md).

> Репозиторий должен быть **доступен без авторизации** (публичный), иначе `curl` к raw-файлу не сработает. Альтернатива: `git clone` + `sudo ./scripts/install_debian.sh --local`.

## Быстрый старт: Windows Server

На Windows Server 2019+ (кратко; детали в [DEPLOYMENT.md](DEPLOYMENT.md)):

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
copy config.example.ini config.ini
```

Отредактируйте `.env` и `config.ini`. Затем проверка и служба:

```bat
.venv\Scripts\python.exe main.py --dry-run
scripts\install_service.bat
```

Web UI: http://127.0.0.1:8787/ (`WEB_USER` / `WEB_PASSWORD` из `.env`).

Файлы с секретами и боевым конфигом в git не попадают.

## Сервисная учётная запись AD

Минимальные права — **только чтение**. Не добавляйте учётку в Domain Admins.

1. Создайте пользователя, например `svc_pwd_notifier`.
2. Оставьте его в группе Domain Users.
3. На нужных OU выдайте чтение свойств и списка объектов user.
4. Если контроллер требует LDAP signing или LDAPS, в `[ad]` укажите `server = ldaps://dc01.domain.local`.
5. Учётки с флагом «пароль не истекает» и без атрибута `mail` пропускаются.
6. `pwdLastSet = 0` — в отчёте «Смена при следующем входе», письмо пользователю не уходит.

Пароль сервисной учётки храните только в `.env` (`AD_SERVICE_PASSWORD`).

## Конфигурация

`config.ini` (копия с `config.example.ini`):

- `[ad]` — сервер, домен, учётка, `search_base`, `excluded_ou` (DN через `;`), `max_pwd_age_days`
- `[notification]` — пороги, путь к CSV, ссылка на инструкцию
- `[smtp]` — релей Exchange или локальный SMTP
- `[admins]` — адреса отчёта через запятую
- `[logging]` — каталог и уровни
- `[schedule]` — `enabled`, `cron` (`0 8 * * *`), `pause_user_mail_until`
- `[web]` — `host`, `port` (по умолчанию `127.0.0.1:8787`)

`.env`:

```
AD_SERVICE_PASSWORD=...
SMTP_USER=...          # необязательно
SMTP_PASSWORD=...      # необязательно
WEB_USER=admin
WEB_PASSWORD=...       # Basic Auth для UI; без пароля auth выключен
```

## Запуск (консоль)

### Linux / Debian

```bash
.venv/bin/python main.py
.venv/bin/python main.py --dry-run
.venv/bin/python main.py --send
.venv/bin/python main.py --serve
```

### Windows

```bat
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe main.py --dry-run
.venv\Scripts\python.exe main.py --send
.venv\Scripts\python.exe main.py --serve
```

## Служба + web UI

### Debian 12 (systemd)

Полный чеклист: [DEPLOYMENT_DEBIAN.md](DEPLOYMENT_DEBIAN.md).

```bash
sudo ./scripts/install_service.sh
sudo systemctl enable --now ad-password-notifier
```

Удаление: `sudo ./scripts/uninstall_service.sh`.

### Windows (NSSM)

Полный чеклист: [DEPLOYMENT.md](DEPLOYMENT.md).

```bat
scripts\install_service.bat
```

Удаление: `scripts\uninstall_service.bat`.

После старта: http://127.0.0.1:8787/

В UI:

1. **Отчёт** — состояние учёток, поиск, «Запустить сейчас» / тестовый прогон.
2. **Настройки** — всё из `config.ini`, пароли в `.env`, проверка LDAP/SMTP.
3. **Пауза рассылки** — не слать письма пользователям до указанной даты.
4. **Напомнить выбранным** — принудительное письмо отмеченным учёткам.

На Windows учётку службы в `services.msc` → Log On задайте доменную с read LDAP.  
На Debian служба работает от `ad-pwd-notifier`; LDAP идёт по NTLM из `config.ini` / `.env`.  
Смена `host`/`port` web требует перезапуска службы; остальные настройки подхватываются после «Сохранить».

## Планировщик (альтернатива без службы)

### Debian (cron)

```bash
sudo crontab -u ad-pwd-notifier -e
# 0 8 * * * cd /opt/ad-password-notifier && .venv/bin/python main.py --send
```

### Windows (Планировщик заданий)

```bat
schtasks /create /tn "AD Password Notifier" /tr "C:\path\to\.venv\Scripts\python.exe C:\path\to\main.py --send" /sc daily /st 08:00 /ru DOMAIN\svc_pwd_notifier
```

Рабочий каталог задачи — корень проекта. Подробности — в [DEPLOYMENT.md](DEPLOYMENT.md) / [DEPLOYMENT_DEBIAN.md](DEPLOYMENT_DEBIAN.md).

## Тесты

```bash
.venv/bin/python -m pytest -q
```

На Windows: `.venv\Scripts\python.exe -m pytest -q`.

Живые LDAP и SMTP в unit-тестах не вызываются.

## Структура проекта

```
DEPLOYMENT.md              # развёртывание на Windows Server
DEPLOYMENT_DEBIAN.md       # развёртывание на Debian 12 + one-line
main.py                    # CLI + пайплайн
service_main.py            # --serve: web + scheduler
scheduler_service.py
report_store.py            # data/last_report.json
config.py / config_writer.py
web/                       # FastAPI UI
scripts/
  install_debian.sh        # онлайн/локальная установка на Debian 12
  install_service.sh       # systemd
  uninstall_service.sh
  ad-password-notifier.service
  install_service.bat      # Windows NSSM
  uninstall_service.bat
templates/                 # письма
tests/
```
