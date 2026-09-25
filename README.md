# Уведомления об истечении паролей AD

Приложение на Python 3.11+ для **Debian 12 / Linux**: проверка срока паролей в локальном Active Directory, HTML-письма пользователям, сводный отчёт администраторам и лёгкий web-интерфейс.

Работает как консольный скрипт (cron) или как **systemd-служба** с встроенным планировщиком и UI. Политики Fine-Grained Password Policies **не учитываются**: используется единый `max_pwd_age_days` из `config.ini`.

**Развёртывание:** [DEPLOYMENT.md](DEPLOYMENT.md)

## Возможности

- Выборка активных пользователей по LDAP (`ldap3` + NTLM).
- Расчёт даты истечения: `pwdLastSet + max_pwd_age_days`.
- Первое письмо при пороге 5 дней, ежедневные — с 3 дней и при просрочке.
- История в CSV, чтобы не дублировать письма и фиксировать смену пароля.
- Сводный HTML-отчёт: истекает скоро / просрочено / пароль сменили.
- Web UI: дашборд, настройки INI, расписание, пауза рассылки, ручное напоминание выбранным.
- Режим службы: один процесс = HTTP + APScheduler (systemd).

## Быстрый старт (Debian 12, one-line)

На сервере с Debian 12:

```bash
curl -fsSL https://raw.githubusercontent.com/blazerity/ad-password-notifier/main/scripts/install_debian.sh | sudo bash
```

Затем отредактируйте `/opt/ad-password-notifier/config.ini` и `.env`, проверьте и запустите:

```bash
sudo -u ad-pwd-notifier /opt/ad-password-notifier/.venv/bin/python /opt/ad-password-notifier/main.py --dry-run
sudo systemctl enable --now ad-password-notifier
```

Web UI: http://127.0.0.1:8787/  
Подробности и ручная установка — [DEPLOYMENT.md](DEPLOYMENT.md).

> Репозиторий должен быть **доступен без авторизации** (публичный), иначе `curl` к raw-файлу не сработает. Альтернатива: `git clone` + `sudo ./scripts/install_debian.sh --local`.

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

```bash
.venv/bin/python main.py
.venv/bin/python main.py --dry-run
.venv/bin/python main.py --send
.venv/bin/python main.py --serve
```

## Служба + web UI (systemd)

```bash
sudo ./scripts/install_service.sh
sudo systemctl enable --now ad-password-notifier
```

Удаление: `sudo ./scripts/uninstall_service.sh`.

После старта: http://127.0.0.1:8787/ (`WEB_USER` / `WEB_PASSWORD` из `.env`).

В UI:

1. **Отчёт** — состояние учёток, поиск, «Запустить сейчас» / тестовый прогон.
2. **Настройки** — всё из `config.ini`, пароли в `.env`, проверка LDAP/SMTP.
3. **Пауза рассылки** — не слать письма пользователям до указанной даты.
4. **Напомнить выбранным** — принудительное письмо отмеченным учёткам.

Служба работает от `ad-pwd-notifier`; LDAP идёт по NTLM из `config.ini` / `.env`.  
Смена `host`/`port` web требует перезапуска службы; остальные настройки подхватываются после «Сохранить».

Полный чеклист: [DEPLOYMENT.md](DEPLOYMENT.md).

## Планировщик (альтернатива без службы)

Только ежедневная рассылка без web UI:

```bash
sudo crontab -u ad-pwd-notifier -e
# 0 8 * * * cd /opt/ad-password-notifier && .venv/bin/python main.py --send
```

Рабочий каталог — корень проекта. Не включайте одновременно cron на `--send` и systemd с `[schedule] enabled = true`.

## Тесты

```bash
.venv/bin/python -m pytest -q
```

Живые LDAP и SMTP в unit-тестах не вызываются.

## Структура проекта

```
DEPLOYMENT.md              # развёртывание на Debian 12 + one-line
main.py                    # CLI
pipeline.py                # пайплайн проверки и рассылки
service_main.py            # --serve: web + scheduler
scheduler_service.py
ad_client.py / mailer.py
report_store.py            # data/last_report.json
config.py / config_writer.py
web/                       # FastAPI UI
scripts/
  install_debian.sh        # онлайн/локальная установка на Debian 12
  install_service.sh       # systemd
  uninstall_service.sh
  ad-password-notifier.service
templates/                 # письма
tests/
```
