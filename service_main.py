"""Режим службы: web UI + планировщик в одном процессе."""

from __future__ import annotations

import logging
import signal
import sys
from typing import Any

import uvicorn

from config import ConfigError, load_config
from pipeline import setup_logging
from scheduler_service import AppScheduler
from web.app import create_app

logger = logging.getLogger(__name__)


class ConfigHolder:
    """Потокобезопасный держатель актуального AppConfig."""

    def __init__(self) -> None:
        self._config = load_config()

    def get(self) -> Any:
        return self._config

    def reload(self) -> Any:
        self._config = load_config()
        return self._config


def serve() -> int:
    """Запустить HTTP и APScheduler. Блокируется до сигнала остановки."""
    try:
        holder = ConfigHolder()
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.critical("Не удалось загрузить конфигурацию: %s", exc)
        return 1

    setup_logging(holder.get())
    config = holder.get()

    if not config.web.password:
        logger.warning(
            "WEB_PASSWORD не задан: Basic Auth выключен. "
            "Рекомендуется задать WEB_USER/WEB_PASSWORD в .env и слушать 127.0.0.1."
        )

    scheduler = AppScheduler(holder.get)

    def reload_and_reschedule() -> Any:
        cfg = holder.reload()
        try:
            scheduler.reschedule()
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось обновить расписание после сохранения настроек")
        return cfg

    app = create_app(get_config=holder.get, reload_config=reload_and_reschedule)
    scheduler.start()

    def _stop(*_args: object) -> None:
        logger.info("Получен сигнал остановки")
        scheduler.shutdown()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("Web UI: http://%s:%s/", config.web.host, config.web.port)
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level="info",
        access_log=False,
    )
    scheduler.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
