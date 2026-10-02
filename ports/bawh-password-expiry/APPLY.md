# Порт модуля «Пароли AD» в bAWH (admin-webhelper) — v0.2.0

Готовый патч для репозитория [blazerity/admin-webhelper](https://github.com/blazerity/admin-webhelper).

Агент cloud не имел прав `push` в `admin-webhelper` (только в `ad-password-notifier`),
поэтому изменения собраны здесь для ручного применения.

## Что сделано

- Раздел **Настройки → Пароли AD**: отчёт, ручной/тестовый прогон, пауза, напоминание выбранным.
- LDAP **не дублируется**: `LDAP_HOST`, `LDAP_BASE_DN`, `LDAP_BIND_DN` / `LDAP_BIND_PASSWORD`, `LDAP_DOMAIN`.
- Новое в `.env`: только `SMTP_*`.
- Пороги, cron, OU-исключения, получатели отчёта — в `app_settings`.
- Миграция `0005_password_expiry`, CLI `flask password-expiry [--dry-run]`, job в `scheduler_worker`.
- `VERSION` → **0.2.0**.

## Применение

В клоне `admin-webhelper`:

```bash
git checkout -b cursor/password-expiry-module-73b8
git am /path/to/ad-password-notifier/ports/bawh-password-expiry/0001-password-expiry-module.patch
# или: скопировать файлы из tree/ поверх корня репозитория
flask --app wsgi db upgrade
```

После деплоя: задать `SMTP_*` в `.env`, в UI включить расписание и получателей отчёта.
Расписание по умолчанию **выключено**.

## Локальная проверка (уже пройдена в сборке)

```bash
python -m pytest -q
# 141 passed
```
