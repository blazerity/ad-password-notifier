from datetime import date

from notification_tracker import HistoryRecord
from report_builder import build_admin_report
from tests.factories import make_user


def test_report_splits_three_sections() -> None:
    users = [
        make_user(username="soon", days_left=4, status="upcoming"),
        make_user(username="late", days_left=-5, status="overdue", email="late@domain.local"),
        make_user(username="ok", days_left=40, status="ok", email="ok@domain.local"),
        make_user(username="logon", days_left=None, status="must_change", snapshot="0"),
    ]
    resolved = [
        HistoryRecord(
            username="fixed",
            email="fixed@domain.local",
            full_name="Fixed User",
            notification_date=date(2026, 9, 18),
            days_left_at_send=179,
            status="resolved",
            pwd_last_set_snapshot="new",
        )
    ]
    report = build_admin_report(users, resolved, first_warning_days=5, today=date(2026, 9, 18))
    assert [row.username for row in report.upcoming] == ["soon"]
    assert {row.username for row in report.overdue} == {"late", "logon"}
    assert report.overdue[0].status_text.startswith("Просрочен") or report.overdue[1].status_text.startswith("Просрочен")
    must = next(row for row in report.overdue if row.username == "logon")
    assert must.status_text == "Смена при следующем входе"
    assert [row.username for row in report.resolved] == ["fixed"]
    assert report.report_date == "2026-09-18"
