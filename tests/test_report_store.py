"""Тесты кэша отчёта и файлового lock."""

from __future__ import annotations

from pathlib import Path

import pytest

from report_builder import AdminReport, ReportRow, build_admin_report
from report_store import build_stored_report, load_report, save_report
from run_lock import RunInProgressError, run_lock
from tests.factories import make_user


def test_save_and_load_report(tmp_path: Path) -> None:
    users = [
        make_user(username="a", days_left=3, status="upcoming"),
        make_user(username="b", days_left=-2, status="overdue"),
    ]
    report = build_admin_report(users, [], first_warning_days=5)
    stored = build_stored_report(report, users, source="test")
    path = tmp_path / "last_report.json"
    save_report(stored, path)
    loaded = load_report(path)
    assert loaded is not None
    assert loaded.counts["upcoming"] == 1
    assert loaded.counts["overdue"] == 1
    assert loaded.all_users[0].username in {"a", "b"}
    assert loaded.source == "test"


def test_run_lock_blocks_second(tmp_path: Path) -> None:
    lock = tmp_path / ".run.lock"
    with run_lock(lock):
        with pytest.raises(RunInProgressError):
            with run_lock(lock):
                pass
    # после выхода lock снят
    with run_lock(lock):
        pass


def test_admin_report_rows_roundtrip_shape() -> None:
    report = AdminReport(
        report_date="2026-09-19",
        upcoming=[ReportRow("A", "a", "a@x", 2, "Осталось 2 дн.")],
        overdue=[],
        resolved=[],
    )
    stored = build_stored_report(report, [], source="x")
    assert stored.upcoming[0].username == "a"
