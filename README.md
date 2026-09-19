# Уведомления об истечении паролей AD

Приложение на Python 3.11+ для Windows Server: проверка срока паролей в локальном Active Directory, HTML-письма пользователям, сводный отчёт администраторам и лёгкий web-интерфейс.

Может работать как консольный скрипт (Планировщик заданий) или как **служба Windows** с встроенным планировщиком и UI. Политики Fine-Grained Password Policies **не учитываются**: используется единый `max_pwd_age_days` из `config.ini`.

## Возможности

- Выборка активных пользователей по LDAP (`ldap3` + NTLM).
- Расчёт даты истечения: `pwdLastSet + max_pwd_age_days`.
- Первое письмо при пороге 5 дней, ежедневные — с 3 дней и при просрочке.
- История в CSV, чтобы не дублировать письма и фиксировать смену пароля.
- Сводный HTML-отчёт: истекает скоро / просрочено / пароль сменили.
- Web UI: дашборд, настройки INI, расписание, пауза рассылки, ручное напоминание выбранным.
- Режим службы: один процесс = HTTP + APScheduler (установка через NSSM).

## Установка

На Windows Server 2019+:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
copy config.example.ini config.ini
```

Отредактируйте `.env` и `config.ini`. Файлы с секретами и боевым конфигом в git не попадают.

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

Из корня проекта:

```bat
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe main.py --dry-run
.venv\Scripts\python.exe main.py --send
```

## Служба Windows + web UI

Рекомендуемый режим на сервере:

```bat
.venv\Scripts\python.exe main.py --serve
```

Или установка службы через [NSSM](https://nssm.cc/download) (от администратора):

```bat
scripts\install_service.bat
```

Удаление: `scripts\uninstall_service.bat`.

После старта откройте `http://127.0.0.1:8787/` (или host/port из `[web]`).

В UI:

1. **Отчёт** — состояние учёток, поиск, «Запустить сейчас» / тестовый прогон.
2. **Настройки** — всё из `config.ini`, пароли в `.env`, проверка LDAP/SMTP.
3. **Пауза рассылки** — не слать письма пользователям до указанной даты.
4. **Напомнить выбранным** — принудительное письмо отмеченным учёткам.

Учётку службы в `services.msc` → Log On задайте доменную с read LDAP (не SYSTEM, если нет доступа к DC).  
Смена `host`/`port` web требует перезапуска службы; остальные настройки подхватываются после «Сохранить».

## Планировщик заданий (альтернатива)

Если служба не нужна:

```bat
schtasks /create /tn "AD Password Notifier" /tr "C:\path\to\.venv\Scripts\python.exe C:\path\to\main.py --send" /sc daily /st 08:00 /ru DOMAIN\svc_pwd_notifier
```

Рабочий каталог задачи — корень проекта.

## Тесты

```bat
.venv\Scripts\python.exe -m pytest -q
```

Живые LDAP и SMTP в unit-тестах не вызываются.

## Структура проекта

```
main.py                 # CLI + пайплайн
service_main.py         # --serve: web + scheduler
scheduler_service.py
report_store.py         # data/last_report.json
config.py / config_writer.py
web/                    # FastAPI UI
scripts/                # install/uninstall NSSM
templates/              # письма
tests/
```
