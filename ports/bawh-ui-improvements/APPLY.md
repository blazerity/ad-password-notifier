# Порт улучшений UI bAWH (admin-webhelper)

Патч для [blazerity/admin-webhelper](https://github.com/blazerity/admin-webhelper).

Cloud-агент пушит только в `ad-password-notifier`; изменения собраны здесь для переноса в основной репозиторий bAWH.

## Зависимости

Сначала примените патч карты сети (если ещё не в main):

```bash
git am /path/to/ad-password-notifier/ports/bawh-network-map-ui/0001-network-map-ui.patch
```

Документация: `docs/ARCHITECTURE.md` (карта сети, маршруты, frontend).

## Что сделано

1. **Автообновление карты** — тумблер вкл/выкл и выбор интервала (30 с … 10 мин, по умолчанию 1 мин). Настройки в `localStorage`. Статусы по-прежнему через `/map/status`, без перезагрузки страницы.
2. **Quick ping на карточках** — кнопка Ping на плитках карты и на карточке устройства (`POST /api/devices/<id>/quick-ping`): ICMP, запись в `device_history`, мгновенное обновление статуса на UI при изменении.
3. **Единые ссылки на сущности** — класс `.bawh-entity-link` (оранжевая обводка) для ссылок на устройства и учётные записи вне карты сети; макросы `macros/entities.html`.

## Применение

```bash
git checkout -b cursor/ui-improvements-f283
git am /path/to/ad-password-notifier/ports/bawh-ui-improvements/0002-ui-improvements.patch
# или скопировать файлы из tree/ поверх корня репозитория
```

Изменённые и новые файлы см. в `0002-ui-improvements.patch` и каталоге `tree/`.

После деплоя перезапустите `bawh-web` (статика и шаблоны).
