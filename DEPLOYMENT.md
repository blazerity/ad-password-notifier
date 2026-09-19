# Развёртывание на Windows Server

Пошаговая инструкция для Windows Server 2019 / 2022 (подойдёт и Windows 10/11 для теста).  
Цель: служба **AD Password Notifier** с web UI и ежедневной проверкой паролей AD.

Рекомендуемый путь установки: `C:\Apps\ad-password-notifier`.

---

## 1. Что понадобится

| Компонент | Зачем |
|---|---|
| Python **3.11+** (x64) | runtime |
| Доступ к репозиторию / архиву проекта | код |
| [NSSM](https://nssm.cc/download) | служба Windows (обёртка над `python main.py --serve`) |
| Учётка AD только на **чтение** | LDAP |
| SMTP-релей (Exchange и т.п.) | письма |
| Права локального администратора на сервере | установка службы |

Docker не нужен.

---

## 2. Сервисная учётка AD

1. Создайте пользователя, например `DOMAIN\svc_pwd_notifier`.
2. **Не** добавляйте в Domain Admins.
3. На нужных OU выдайте права чтения списка объектов и свойств user.
4. Пароль этой учётки потом попадёт только в `.env` (`AD_SERVICE_PASSWORD`).

Проверка с рабочей станции (по желанию):

```bat
nltest /dsgetdc:DOMAIN
```

---

## 3. Установка Python

1. Скачайте Python 3.11+ x64 с [python.org](https://www.python.org/downloads/windows/).
2. При установке включите **Add python.exe to PATH**.
3. Проверьте:

```bat
py -3.11 --version
```

---

## 4. Код приложения

### Вариант A — git

```bat
mkdir C:\Apps
cd C:\Apps
git clone <URL-репозитория> ad-password-notifier
cd ad-password-notifier
```

### Вариант B — архив

Распакуйте релиз/ветку в `C:\Apps\ad-password-notifier`.

---

## 5. Виртуальное окружение и зависимости

В **cmd** от имени пользователя, который будет администрировать приложение:

```bat
cd C:\Apps\ad-password-notifier
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Проверка импорта:

```bat
.venv\Scripts\python.exe -c "import fastapi, ldap3, apscheduler; print('OK')"
```

---

## 6. Конфигурация

```bat
copy config.example.ini config.ini
copy .env.example .env
```

Отредактируйте файлы в блокноте или через web UI после первого старта.

### 6.1. `config.ini` — минимум

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

- Для LDAPS: `server = ldaps://dc01.domain.local`.
- `cron` — 5 полей: `минута час день месяц день_недели` (пример выше = каждый день в 08:00).
- `host = 127.0.0.1` — UI только с этого сервера. Для доступа с других ПК во внутренней сети: `0.0.0.0` + firewall + **обязательно** `WEB_PASSWORD`.

### 6.2. `.env` — секреты

```env
AD_SERVICE_PASSWORD=********
WEB_USER=admin
WEB_PASSWORD=********

# Необязательно: иначе SMTP AUTH = from_address + AD_SERVICE_PASSWORD
# SMTP_USER=noreply@domain.local
# SMTP_PASSWORD=********
```

Права на `.env`: только администраторы сервера / учётка службы.

---

## 7. Проверка до установки службы

Из корня проекта:

```bat
cd C:\Apps\ad-password-notifier
.venv\Scripts\python.exe main.py --dry-run
```

Ожидаемо:

- подключение к AD;
- HTML-превью в `data\previews\`;
- SMTP и CSV **не** трогаются.

Боевой разовый прогон:

```bat
.venv\Scripts\python.exe main.py --send
```

Ручной запуск UI (без службы):

```bat
.venv\Scripts\python.exe main.py --serve
```

Откройте в браузере на сервере: http://127.0.0.1:8787/  
Логин/пароль — из `.env` (`WEB_USER` / `WEB_PASSWORD`).

Остановка: `Ctrl+C` в консоли.

---

## 8. Установка как службы Windows (NSSM)

### 8.1. NSSM

1. Скачайте NSSM: https://nssm.cc/download  
2. Из архива возьмите `nssm.exe` для вашей разрядности (`win64`).
3. Либо положите в `C:\Apps\ad-password-notifier\scripts\nssm.exe`, либо добавьте каталог с `nssm.exe` в PATH.

### 8.2. Установка

Запустите **cmd от имени администратора**:

```bat
cd C:\Apps\ad-password-notifier
scripts\install_service.bat
```

Скрипт создаёт службу `ADPasswordNotifier`, рабочий каталог = корень проекта, автозапуск, логи:

- `logs\service_stdout.log`
- `logs\service_stderr.log`

### 8.3. Учётка службы (Log On)

1. `Win+R` → `services.msc`
2. Служба **AD Password Notifier** → свойства → **Вход в систему**
3. Укажите `DOMAIN\svc_pwd_notifier` и пароль  
   **Не используйте Local System**, если у SYSTEM нет нормального доступа к DC.
4. Перезапустите службу:

```bat
nssm restart ADPasswordNotifier
```

или через `services.msc`.

### 8.4. Firewall (если UI нужен с других ПК)

Только после смены `[web] host = 0.0.0.0` и сильного `WEB_PASSWORD`:

```bat
netsh advfirewall firewall add rule name="AD Password Notifier UI" dir=in action=allow protocol=TCP localport=8787
```

---

## 9. Web UI после развёртывания

| Страница | Назначение |
|---|---|
| **Отчёт** | состояние учёток, «Запустить сейчас», тестовый прогон, пауза, ручные напоминания |
| **Настройки** | AD / SMTP / пороги / cron / web; кнопки «Проверить LDAP» и «Проверить SMTP» |

После «Сохранить» большинство параметров подхватываются без рестарта.  
Смена `host` / `port` web — нужен перезапуск службы.

---

## 10. Обновление версии

```bat
cd C:\Apps\ad-password-notifier
nssm stop ADPasswordNotifier

git pull
REM или замените файлы из нового архива, сохранив config.ini и .env

.venv\Scripts\python.exe -m pip install -r requirements.txt
nssm start ADPasswordNotifier
```

`config.ini`, `.env`, `data\notification_history.csv` в git не коммитьте — они должны остаться на сервере.

---

## 11. Удаление службы

```bat
cd C:\Apps\ad-password-notifier
scripts\uninstall_service.bat
```

Каталог приложения и данные при этом не удаляются.

---

## 12. Альтернатива без службы (Планировщик заданий)

Если web UI не нужен — только ежедневная рассылка:

```bat
schtasks /create /tn "AD Password Notifier" /tr "C:\Apps\ad-password-notifier\.venv\Scripts\python.exe C:\Apps\ad-password-notifier\main.py --send" /sc daily /st 08:00 /ru DOMAIN\svc_pwd_notifier
```

В свойствах задачи укажите **начальную папку** = `C:\Apps\ad-password-notifier`.

---

## 13. Диагностика

| Симптом | Куда смотреть |
|---|---|
| Служба не стартует | `logs\service_stderr.log`, Event Viewer → Windows Logs → Application |
| Нет LDAP | `[ad]` в `config.ini`, пароль в `.env`, Log On службы, LDAPS |
| Нет писем | `[smtp]`, `SMTP_USER`/`SMTP_PASSWORD`, права на relay |
| UI 401 / без пароля | `WEB_PASSWORD` в `.env` |
| UI не открывается с другого ПК | `[web] host`, firewall, порт |
| Двойной прогон | не держите одновременно службу и schtasks на `--send` |

Ручной тест связей из UI: **Настройки → Проверить LDAP / Проверить SMTP**.

Логи приложения: `logs\ad_password_notifier_*.log`.

Коды выхода прогона: `0` — ок, `1` — ошибка конфига/AD/SMTP-отчёта, `2` — уже идёт другой прогон.

---

## 14. Чеклист готовности

- [ ] Python 3.11+ установлен  
- [ ] `.venv` и `pip install -r requirements.txt`  
- [ ] Заполнены `config.ini` и `.env`  
- [ ] `--dry-run` успешен  
- [ ] NSSM: служба установлена и Running  
- [ ] Log On = доменная учётка с read LDAP  
- [ ] UI открывается, Basic Auth работает  
- [ ] В UI проверка LDAP/SMTP — OK  
- [ ] В `[schedule]` нужный cron, `enabled = true`  
- [ ] Получатели в `[admins]` корректны  
