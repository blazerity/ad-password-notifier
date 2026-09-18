"""Загрузка и валидация конфигурации из config.ini и .env."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
LOGGER_NAME = "ad_password_notifier"


@dataclass(frozen=True)
class AdConfig:
    """Параметры подключения к Active Directory."""

    server: str
    domain: str
    service_user: str
    service_password: str
    search_base: str
    excluded_ou: list[str]
    max_pwd_age_days: int


@dataclass(frozen=True)
class NotificationConfig:
    """Пороги уведомлений и путь к CSV-истории."""

    first_warning_days: int
    daily_warning_threshold: int
    history_csv: Path
    instructions_url: str


@dataclass(frozen=True)
class SmtpConfig:
    """Параметры SMTP-отправки."""

    host: str
    port: int
    use_tls: bool
    use_starttls: bool
    from_address: str
    username: str | None
    password: str | None


@dataclass(frozen=True)
class AdminsConfig:
    """Получатели административного отчёта и алертов."""

    recipients: list[str]


@dataclass(frozen=True)
class LoggingConfig:
    """Параметры ylogger."""

    log_dir: Path
    file_level: str
    console_level: str
    max_log_age: int
    use_emoji: bool


@dataclass(frozen=True)
class AppConfig:
    """Полная конфигурация приложения."""

    ad: AdConfig
    notification: NotificationConfig
    smtp: SmtpConfig
    admins: AdminsConfig
    logging: LoggingConfig


class ConfigError(ValueError):
    """Некорректная или неполная конфигурация."""


def _require(section: configparser.SectionProxy, key: str, context: str) -> str:
    value = section.get(key, fallback="").strip()
    if not value:
        raise ConfigError(f"Отсутствует обязательный параметр [{context}] {key}")
    return value


def _split_list(raw: str, sep: str = ",") -> list[str]:
    return [item.strip() for item in raw.split(sep) if item.strip()]


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def load_config(config_path: Path | None = None, env_path: Path | None = None) -> AppConfig:
    """Загрузить INI-конфиг и секреты из .env.

    Args:
        config_path: путь к config.ini (по умолчанию рядом с модулем).
        env_path: путь к .env (по умолчанию PROJECT_ROOT/.env).
    """
    load_dotenv(env_path or (PROJECT_ROOT / ".env"))

    ini_path = config_path or (PROJECT_ROOT / "config.ini")
    if not ini_path.is_file():
        raise ConfigError(f"Файл конфигурации не найден: {ini_path}")

    parser = configparser.ConfigParser()
    read = parser.read(ini_path, encoding="utf-8")
    if not read:
        raise ConfigError(f"Не удалось прочитать {ini_path}")

    for section_name in ("ad", "notification", "smtp", "admins", "logging"):
        if not parser.has_section(section_name):
            raise ConfigError(f"В config.ini нет секции [{section_name}]")

    ad_raw = parser["ad"]
    note_raw = parser["notification"]
    smtp_raw = parser["smtp"]
    admins_raw = parser["admins"]
    log_raw = parser["logging"]

    password = os.getenv("AD_SERVICE_PASSWORD", "").strip()
    if not password:
        raise ConfigError("Не задан AD_SERVICE_PASSWORD в .env")

    recipients = _split_list(admins_raw.get("recipients", ""))
    if not recipients:
        raise ConfigError("[admins] recipients должен быть непустым списком")

    max_pwd_age = int(_require(ad_raw, "max_pwd_age_days", "ad"))
    first_warning = int(_require(note_raw, "first_warning_days", "notification"))
    daily_threshold = int(_require(note_raw, "daily_warning_threshold", "notification"))
    if max_pwd_age <= 0 or first_warning <= 0 or daily_threshold <= 0:
        raise ConfigError("Пороги дней должны быть положительными числами")
    if daily_threshold > first_warning:
        raise ConfigError("daily_warning_threshold не может быть больше first_warning_days")

    smtp_user = os.getenv("SMTP_USER", "").strip() or None
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip() or None

    return AppConfig(
        ad=AdConfig(
            server=_require(ad_raw, "server", "ad"),
            domain=_require(ad_raw, "domain", "ad"),
            service_user=_require(ad_raw, "service_user", "ad"),
            service_password=password,
            search_base=_require(ad_raw, "search_base", "ad"),
            excluded_ou=_split_list(ad_raw.get("excluded_ou", ""), sep=";"),
            max_pwd_age_days=max_pwd_age,
        ),
        notification=NotificationConfig(
            first_warning_days=first_warning,
            daily_warning_threshold=daily_threshold,
            history_csv=_resolve_path(_require(note_raw, "history_csv", "notification")),
            instructions_url=note_raw.get("instructions_url", fallback="").strip(),
        ),
        smtp=SmtpConfig(
            host=_require(smtp_raw, "host", "smtp"),
            port=int(_require(smtp_raw, "port", "smtp")),
            use_tls=smtp_raw.getboolean("use_tls", fallback=False),
            use_starttls=smtp_raw.getboolean("use_starttls", fallback=False),
            from_address=_require(smtp_raw, "from_address", "smtp"),
            username=smtp_user,
            password=smtp_password,
        ),
        admins=AdminsConfig(recipients=recipients),
        logging=LoggingConfig(
            log_dir=_resolve_path(log_raw.get("log_dir", fallback="logs").strip() or "logs"),
            file_level=(log_raw.get("file_level", fallback="DEBUG") or "DEBUG").upper(),
            console_level=(log_raw.get("console_level", fallback="INFO") or "INFO").upper(),
            max_log_age=int(log_raw.get("max_log_age", fallback="30") or 30),
            use_emoji=log_raw.getboolean("use_emoji", fallback=True),
        ),
    )
