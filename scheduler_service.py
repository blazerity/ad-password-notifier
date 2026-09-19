"""Планировщик ежедневных прогонов (APScheduler)."""

from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_pipeline

logger = logging.getLogger(__name__)


def _local_timezone():
    """Локальная TZ без строки 'local' (zoneinfo её не понимает)."""
    try:
        from tzlocal import get_localzone

        return get_localzone()
    except Exception:  # noqa: BLE001
        return dt_timezone.utc


def _parse_cron(cron: str) -> CronTrigger:
    """Поддержать классический 5-польный cron: min hour dom month dow."""
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"Ожидается 5 полей cron, получено: {cron!r}")
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )


class AppScheduler:
    """Фоновый планировщик, читающий конфиг через callback."""

    def __init__(self, get_config: Callable[[], AppConfig]) -> None:
        self._get_config = get_config
        self._scheduler = BackgroundScheduler(timezone=_local_timezone())
        self._job_id = "daily_password_check"

    def start(self) -> None:
        self.reschedule()
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Планировщик запущен")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Планировщик остановлен")

    def reschedule(self) -> None:
        config = self._get_config()
        if self._scheduler.get_job(self._job_id):
            self._scheduler.remove_job(self._job_id)

        if not config.schedule.enabled:
            logger.info("Автопроверка отключена в [schedule]")
            return

        trigger = _parse_cron(config.schedule.cron)
        self._scheduler.add_job(
            self._job,
            trigger=trigger,
            id=self._job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Расписание автопроверки: %s", config.schedule.cron)

    def _job(self) -> None:
        config = self._get_config()
        if not config.schedule.enabled:
            logger.info("Пропуск по расписанию: schedule.enabled=false")
            return
        logger.info("Старт плановой проверки паролей")
        result = run_pipeline(config, send_emails=True, mode="scheduled")
        logger.info(
            "Плановая проверка завершена: exit=%s sent=%s",
            result.exit_code,
            result.sent_count,
        )

    @property
    def next_run_time(self) -> str | None:
        job = self._scheduler.get_job(self._job_id)
        if not job or not job.next_run_time:
            return None
        return job.next_run_time.isoformat()
