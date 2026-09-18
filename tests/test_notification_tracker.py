from datetime import date
from pathlib import Path

from notification_tracker import HistoryRecord, NotificationTracker
from tests.factories import make_user


def _tracker(tmp_path: Path) -> NotificationTracker:
    return NotificationTracker(tmp_path / "history.csv")


def test_first_warning_at_five_days(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    user = make_user(days_left=5, status="upcoming", snapshot="pwd-1")
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "send"
    assert decision.status == "upcoming"


def test_no_daily_mail_between_first_and_daily_threshold(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    user = make_user(days_left=4, status="upcoming", snapshot="pwd-1")
    tracker.append(user, status="upcoming", today=date(2026, 9, 17))
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "skip"


def test_daily_mail_from_three_days(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    user = make_user(days_left=3, status="upcoming", snapshot="pwd-1")
    tracker.append(user, status="upcoming", today=date(2026, 9, 16))
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "send"
    assert decision.status == "upcoming"


def test_overdue_daily_mail(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    user = make_user(days_left=-2, status="overdue", snapshot="pwd-1")
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "send"
    assert decision.status == "overdue"


def test_no_duplicate_same_day(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    today = date(2026, 9, 18)
    user = make_user(days_left=2, status="upcoming", snapshot="pwd-1")
    tracker.append(user, status="upcoming", today=today)
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=today)
    assert decision.action == "skip"


def test_resolved_when_password_changed(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    old = make_user(days_left=-1, status="overdue", snapshot="pwd-old")
    tracker.append(old, status="overdue", today=date(2026, 9, 17))
    changed = make_user(days_left=179, status="ok", snapshot="pwd-new")
    decision = tracker.decide(changed, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "resolve"
    assert decision.status == "resolved"


def test_must_change_does_not_send(tmp_path: Path) -> None:
    tracker = _tracker(tmp_path)
    user = make_user(days_left=None, status="must_change", snapshot="0")
    decision = tracker.decide(user, first_warning_days=5, daily_warning_threshold=3, today=date(2026, 9, 18))
    assert decision.action == "skip"


def test_roundtrip_csv(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    tracker = NotificationTracker(path)
    user = make_user()
    tracker.append(user, status="upcoming", today=date(2026, 9, 18))
    tracker.save()
    loaded = NotificationTracker(path)
    assert len(loaded.records_for("jdoe")) == 1
    assert loaded.last_record("jdoe") == HistoryRecord(
        username="jdoe",
        email="jdoe@domain.local",
        full_name="John Doe",
        notification_date=date(2026, 9, 18),
        days_left_at_send=5,
        status="upcoming",
        pwd_last_set_snapshot="111",
    )
