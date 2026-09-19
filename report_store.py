"""Кэш последнего отчёта и статуса прогона (JSON)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ad_client import AdUser
from config import PROJECT_ROOT
from report_builder import AdminReport, ReportRow

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "last_report.json"
DEFAULT_STATUS_PATH = PROJECT_ROOT / "data" / "last_run_status.json"


@dataclass
class ReportUserSnapshot:
    """Снимок учётки для дашборда."""

    username: str
    email: str
    full_name: str
    days_left: int | None
    status: str
    status_text: str
    expiry_date: str | None = None
    distinguished_name: str = ""


@dataclass
class StoredReport:
    """Последний сохранённый отчёт."""

    report_date: str
    generated_at: str
    upcoming: list[ReportUserSnapshot] = field(default_factory=list)
    overdue: list[ReportUserSnapshot] = field(default_factory=list)
    resolved: list[ReportUserSnapshot] = field(default_factory=list)
    all_users: list[ReportUserSnapshot] = field(default_factory=list)
    source: str = "run"

    @property
    def counts(self) -> dict[str, int]:
        return {
            "upcoming": len(self.upcoming),
            "overdue": len(self.overdue),
            "resolved": len(self.resolved),
            "total": len(self.all_users),
        }


@dataclass
class RunStatus:
    """Статус последнего прогона."""

    started_at: str
    finished_at: str
    exit_code: int
    send_emails: bool
    user_mail_paused: bool
    users_count: int
    sent_count: int
    resolved_count: int
    upcoming_count: int
    overdue_count: int
    error: str = ""
    mode: str = "scheduled"


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def _row_to_snapshot(row: ReportRow, status: str) -> ReportUserSnapshot:
    return ReportUserSnapshot(
        username=row.username,
        email=row.email,
        full_name=row.full_name,
        days_left=row.days_left,
        status=status,
        status_text=row.status_text,
    )


def _user_to_snapshot(user: AdUser, status_text: str | None = None) -> ReportUserSnapshot:
    if status_text is None:
        if user.status == "must_change":
            status_text = "Смена при следующем входе"
        elif user.status == "overdue":
            days = 0 if user.days_left is None else abs(user.days_left)
            status_text = f"Просрочен на {days} дн."
        elif user.status == "upcoming" and user.days_left is not None:
            status_text = f"Осталось {user.days_left} дн."
        else:
            status_text = "В норме"
    return ReportUserSnapshot(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        days_left=user.days_left,
        status=user.status,
        status_text=status_text,
        expiry_date=user.expiry_date.isoformat() if user.expiry_date else None,
        distinguished_name=user.distinguished_name,
    )


def build_stored_report(
    report: AdminReport,
    users: list[AdUser],
    *,
    source: str = "run",
) -> StoredReport:
    """Собрать StoredReport из AdminReport и полного списка пользователей."""
    upcoming = [_row_to_snapshot(row, "upcoming") for row in report.upcoming]
    overdue = [_row_to_snapshot(row, "overdue") for row in report.overdue]
    resolved = [_row_to_snapshot(row, "resolved") for row in report.resolved]
    return StoredReport(
        report_date=report.report_date,
        generated_at=_iso_now(),
        upcoming=upcoming,
        overdue=overdue,
        resolved=resolved,
        all_users=[_user_to_snapshot(user) for user in users],
        source=source,
    )


def save_report(stored: StoredReport, path: Path | None = None) -> Path:
    """Записать отчёт в JSON."""
    target = path or DEFAULT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(stored)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Отчёт сохранён: %s", target)
    return target


def load_report(path: Path | None = None) -> StoredReport | None:
    """Прочитать последний отчёт или None."""
    target = path or DEFAULT_REPORT_PATH
    if not target.is_file():
        return None
    try:
        raw: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Не удалось прочитать отчёт %s: %s", target, exc)
        return None
    return StoredReport(
        report_date=str(raw.get("report_date") or date.today().isoformat()),
        generated_at=str(raw.get("generated_at") or ""),
        upcoming=[ReportUserSnapshot(**item) for item in raw.get("upcoming") or []],
        overdue=[ReportUserSnapshot(**item) for item in raw.get("overdue") or []],
        resolved=[ReportUserSnapshot(**item) for item in raw.get("resolved") or []],
        all_users=[ReportUserSnapshot(**item) for item in raw.get("all_users") or []],
        source=str(raw.get("source") or "run"),
    )


def save_run_status(status: RunStatus, path: Path | None = None) -> Path:
    """Сохранить статус последнего прогона."""
    target = path or DEFAULT_STATUS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_run_status(path: Path | None = None) -> RunStatus | None:
    """Прочитать статус последнего прогона."""
    target = path or DEFAULT_STATUS_PATH
    if not target.is_file():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return RunStatus(**raw)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Не удалось прочитать статус прогона %s: %s", target, exc)
        return None
