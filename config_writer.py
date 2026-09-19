"""Сохранение config.ini и обновление секретов в .env."""

from __future__ import annotations

import configparser
from pathlib import Path

from config import DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH, ConfigError, PROJECT_ROOT


def save_ini_settings(
    values: dict[str, dict[str, str]],
    *,
    config_path: Path | None = None,
) -> None:
    """Обновить секции INI, сохранив прочие ключи."""
    ini_path = config_path or DEFAULT_CONFIG_PATH
    parser = configparser.ConfigParser()
    if ini_path.is_file():
        read = parser.read(ini_path, encoding="utf-8")
        if not read:
            raise ConfigError(f"Не удалось прочитать {ini_path}")

    for section, items in values.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, raw in items.items():
            parser.set(section, key, str(raw))

    ini_path.parent.mkdir(parents=True, exist_ok=True)
    with ini_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def update_env_secrets(
    updates: dict[str, str],
    *,
    env_path: Path | None = None,
) -> None:
    """Создать или обновить ключи в .env. Пустые значения не меняют существующий секрет."""
    path = env_path or DEFAULT_ENV_PATH
    filtered = {key: str(value).strip() for key, value in updates.items() if str(value or "").strip()}
    if not filtered:
        return

    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                lines.append(line)
                continue
            key = line.partition("=")[0].strip()
            if key in filtered:
                lines.append(f"{key}={filtered[key]}")
                seen.add(key)
            else:
                lines.append(line)

    for key, value in filtered.items():
        if key not in seen:
            lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def relative_to_project(path: Path) -> str:
    """Путь для записи в INI: относительно корня проекта, если возможно."""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)
