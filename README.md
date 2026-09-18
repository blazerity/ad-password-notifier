# Уведомления об истечении паролей AD

Консольное приложение на Python 3.11+ для Windows: ежедневная проверка срока паролей в локальном Active Directory, HTML-письма пользователям и сводный отчёт администраторам.

Запускается по расписанию через Планировщик заданий Windows, не как служба. Политики Fine-Grained Password Policies **не учитываются**: используется единый `max_pwd_age_days` из `config.ini` (в домене — 180 дней).

## Возможности

- Выборка активных пользователей по LDAP (`ldap3` и `pycryptodome` для NTLM/MD4 на Python 3.12+; без pywin32 и модуля Active Directory в PowerShell).
- Расчёт даты истечения: `pwdLastSet + max_pwd_age_days`.
- Первое письмо при пороге 5 дней, ежедневные письма начиная с 3 дней и при просрочке.
- История в CSV, чтобы не дублировать письма и фиксировать смену пароля (`pwdLastSet`).
- Сводный HTML-отчёт: истекает скоро / просрочено / пароль сменили.
- Алерт администраторам, если недоступны AD или SMTP.
- Тестовый прогон без отправки почты (меню в консоли или `--dry-run`).

## Установка

На Windows 10 / Windows Server 2019:

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
5. Учётки с флагом «пароль не истекает» и без атрибута `mail` пропускаются (в лог пишется предупреждение).
6. `pwdLastSet = 0` (смена при следующем входе) не считается истечением через 180 дней: в отчёте будет статус «Смена при следующем входе», письмо пользователю не уходит.

Пароль сервисной учётки храните только в `.env` (`AD_SERVICE_PASSWORD`).

## Конфигурация

`config.ini` (копия с `config.example.ini`):

- `[ad]` — сервер, домен, учётка, `search_base`, `excluded_ou` (несколько DN через `;`), `max_pwd_age_days`
- `[notification]` — пороги 5 и 3 дня, путь к CSV, ссылка на инструкцию
- `[smtp]` — релей Exchange или локальный SMTP, не Outlook
- `[admins]` — адреса отчёта через запятую
- `[logging]` — каталог и уровни для `ylogger.py`

`.env`:

```
AD_SERVICE_PASSWORD=...
SMTP_USER=...          # необязательно: иначе [smtp] from_address
SMTP_PASSWORD=...      # необязательно: иначе AD_SERVICE_PASSWORD
```

Exchange на порту 587 требует SMTP AUTH. Если `SMTP_USER`/`SMTP_PASSWORD` не заданы, вход идёт той же сервисной учёткой, что и LDAP (`from_address` + `AD_SERVICE_PASSWORD`). `use_tls` / `use_starttls` включают STARTTLS (как в equipment-csv-mailer), не SMTPS на 465.

## Правила писем пользователю

| Состояние | Действие |
| --- | --- |
| Осталось не больше 5 дней, в этом цикле ещё не писали | одно первое письмо |
| Осталось 3 дня и меньше либо пароль уже просрочен | письмо каждый день |
| За сегодня запись уже есть | повтор не отправляется |
| `pwdLastSet` изменился | цикл закрывается статусом `resolved` |

История: `data/notification_history.csv`.

## Запуск

Из корня проекта (рядом должны быть `config.ini` и `templates/`):

```bat
.venv\Scripts\python.exe main.py
```

В интерактивной консоли:

```
1) Боевой запуск — LDAP и отправка писем
2) Тестовый прогон — LDAP, без SMTP и без записи истории
0) Выход
```

По умолчанию выбран пункт 2.

Без меню:

```bat
python main.py --dry-run
python main.py --send
```

Тестовый прогон ходит в AD, пишет HTML в `data/previews/` и не трогает SMTP и CSV.

Логи: `logs/ad_password_notifier_ГГГГММДД_ЧЧММСС.log` (файлы старше `max_log_age` дней удаляются).

## Планировщик заданий Windows

Для автозапуска укажите `--send`:

```bat
schtasks /create /tn "AD Password Notifier" /tr "C:\path\to\python.exe C:\path\to\main.py --send" /sc daily /st 08:00 /ru SYSTEM
```

Рекомендации:

- Рабочий каталог задачи — корень проекта, иначе не найдутся INI и шаблоны.
- Учётка задачи должна уметь читать LDAP. SYSTEM часто не подходит, если у него нет доступа к контроллеру домена.
- Код выхода `1` — ошибка конфигурации, AD или отправки отчёта.

## Тесты

```bat
.venv\Scripts\python.exe -m pytest -q
```

Живые LDAP и SMTP в unit-тестах не вызываются.

## Структура проекта

```
main.py
ylogger.py
config.py
config.example.ini
.env.example
ad_client.py
mailer.py
notification_tracker.py
report_builder.py
templates/
tests/
```
