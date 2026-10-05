# Порт улучшений карты сети в bAWH (admin-webhelper)

Готовый патч для репозитория [blazerity/admin-webhelper](https://github.com/blazerity/admin-webhelper).

Cloud-агент не имеет прав `push` в `admin-webhelper` (только в `ad-password-notifier`),
поэтому изменения собраны здесь для переноса в основной репозиторий bAWH.

## Что сделано

- **Вид карты** (как переключатель на витринах): список, прямоугольные карточки (как сейчас), крупные квадратные плитки.
- **Сортировка** внутри сектора: по hostname, по IP, по MAC.
- **Фильтры по умолчанию**: включены только «Ноутбуки» и «СБ»; кнопка «Сбросить» возвращает этот набор.
- Выбранные вид и сортировка сохраняются в `localStorage` и отражаются в URL (`layout`, `sort`).

Документация продукта: `docs/ARCHITECTURE.md` (раздел «Карта сети UI»).

## Применение

В клоне `admin-webhelper`:

```bash
git checkout -b cursor/network-map-ui-9dea
git am /path/to/ad-password-notifier/ports/bawh-network-map-ui/0001-network-map-ui.patch
# или: скопировать файлы из tree/ поверх корня репозитория
```

Изменённые файлы:

- `app/templates/devices/map.html`
- `app/static/js/map.js`
- `app/static/css/app.css`

После деплоя достаточно обновить статику (перезапуск `bawh-web`).
