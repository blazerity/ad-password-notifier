"""Чтение и запись CSV-истории уведомлений, дедупликация и закрытие циклов."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Literal

from ad_client import AdUser

logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "username",
    "email",
    "full_name",
    "notification_date",
    "days_left_at_send",
    "status",
    "pwd_last_set_snapshot",
]

NotificationStatus = Literal["upcoming", "overdue", "resolved"]
NotifyAction = Literal["send", "skip", "resolve"]


@dataclass(frozen=True)
class HistoryRecord:
    """Одна строка CSV-истории."""

    username: str
    email: str
    full_name: str
    notification_date: date
    days_left_at_send: int | None
    status: NotificationStatus
    pwd_last_set_snapshot: str


@dataclass(frozen=True)
class NotifyDecision:
    """Решение по пользователю на текущий прогон."""

    action: NotifyAction
    status: NotificationStatus | None
    reason: str


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _parse_days(raw: str) -> int | None:
    text = (raw or "").strip()
    if text == "":
        return None
    return int(text)


class NotificationTracker:
    """Хранит историю писем и решает, нужно ли уведомлять пользователя."""

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._records: list[HistoryRecord] = []
        self.load()

    def load(self) -> None:
        """Прочитать CSV, если файл существует."""
        self._records = []
        if not self.csv_path.is_file():
            logger.info("Файл истории отсутствует, будет создан: %s", self.csv_path)
            return
        with self.csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not row.get("username"):
                    continue
                self._records.append(
                    HistoryRecord(
                        username=row["username"],
                        email=row.get("email", ""),
                        full_name=row.get("full_name", ""),
                        notification_date=_parse_date(row["notification_date"]),
                        days_left_at_send=_parse_days(row.get("days_left_at_send", "")),
                        status=row["status"],  # type: ignore[arg-type]
                        pwd_last_set_snapshot=str(row.get("pwd_last_set_snapshot", "")),
                    )
                )
        logger.info("Загружено записей истории: %s", len(self._records))

    def save(self) -> None:
        """Перезаписать CSV актуальным набором записей."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in self._records:
                writer.writerow(
                    {
                        "username": record.username,
                        "email": record.email,
                        "full_name": record.full_name,
                        "notification_date": record.notification_date.isoformat(),
                        "days_left_at_send": (
                            "" if record.days_left_at_send is None else record.days_left_at_send
                        ),
                        "status": record.status,
                        "pwd_last_set_snapshot": record.pwd_last_set_snapshot,
                    }
                )

    def records_for(self, username: str) -> list[HistoryRecord]:
        """Все записи пользователя в хронологическом порядке."""
        return [item for item in self._records if item.username.lower() == username.lower()]

    def last_record(self, username: str) -> HistoryRecord | None:
        """Последняя запись пользователя или None."""
        items = self.records_for(username)
        return items[-1] if items else None

    def already_sent_today(self, username: str, today: date) -> bool:
        """True, если сегодня уже есть неотменённая отправка пользователю."""
        return any(
            item.username.lower() == username.lower()
            and item.notification_date == today
            and item.status in {"upcoming", "overdue"}
            for item in self._records
        )

    def decide(
        self,
        user: AdUser,
        *,
        first_warning_days: int,
        daily_warning_threshold: int,
        today: date | None = None,
    ) -> NotifyDecision:
        """Определить действие: отправить письмо, пропустить или закрыть цикл."""
        current = today or date.today()
        last = self.last_record(user.username)

        if user.status == "must_change":
            return NotifyDecision("skip", None, "требуется смена при входе, письмо не отправляем")

        if last and last.status != "resolved" and last.pwd_last_set_snapshot != user.pwd_last_set_snapshot:
            if user.status == "ok":
                return NotifyDecision("resolve", "resolved", "пароль сменён, цикл уведомлений закрыт")
            # Новый цикл уже снова в зоне предупреждения — сначала закрываем старый.
            return NotifyDecision("resolve", "resolved", "пароль сменён, фиксируем resolved")

        if user.status == "ok":
            return NotifyDecision("skip", None, "срок пароля вне окна уведомлений")

        if self.already_sent_today(user.username, current):
            return NotifyDecision("skip", None, "письмо уже отправлено сегодня")

        cycle_records = [
            item
            for item in self.records_for(user.username)
            if item.pwd_last_set_snapshot == user.pwd_last_set_snapshot and item.status != "resolved"
        ]
        sent_in_cycle = any(item.status in {"upcoming", "overdue"} for item in cycle_records)

        if user.status == "overdue" or (
            user.days_left is not None and user.days_left <= daily_warning_threshold
        ):
            send_status: NotificationStatus = "overdue" if user.status == "overdue" else "upcoming"
            return NotifyDecision("send", send_status, "ежедневное предупреждение")

        if user.status == "upcoming" and user.days_left is not None:
            if user.days_left <= first_warning_days and not sent_in_cycle:
                return NotifyDecision("send", "upcoming", "первое предупреждение")
            return NotifyDecision("skip", None, "первое письмо уже отправлено, ежедневный порог не достигнут")

        return NotifyDecision("skip", None, "нет правила отправки")

    def append(
        self,
        user: AdUser,
        *,
        status: NotificationStatus,
        today: date | None = None,
    ) -> HistoryRecord:
        """Добавить запись в историю (без немедленной записи на диск)."""
        current = today or date.today()
        record = HistoryRecord(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            notification_date=current,
            days_left_at_send=user.days_left,
            status=status,
            pwd_last_set_snapshot=user.pwd_last_set_snapshot
            if status != "resolved"
            else user.pwd_last_set_snapshot,
        )
        self._records.append(record)
        return record

    def resolved_today(self, today: date | None = None) -> list[HistoryRecord]:
        """Записи resolved, закрытые в указанный день."""
        current = today or date.today()
        return [
            item
            for item in self._records
            if item.status == "resolved" and item.notification_date == current
        ]

    def extend(self, records: Iterable[HistoryRecord]) -> None:
        """Добавить готовые записи (для тестов)."""
        self._records.extend(records)
