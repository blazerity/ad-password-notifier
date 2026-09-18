from datetime import date, datetime, timezone

from ad_client import (
    UAC_PASSWORD_NEVER_EXPIRES,
    classify_user,
    compute_days_left,
    filetime_to_datetime,
    snapshot_pwd_last_set,
)

WINDOWS_EPOCH_FILETIME = 132_000_000_000_000_000  # arbitrary valid FILETIME


def test_filetime_zero_is_must_change() -> None:
    assert filetime_to_datetime(0) is None
    assert filetime_to_datetime(None) is None
    assert snapshot_pwd_last_set(0) == "0"


def test_filetime_int_converts_to_utc_datetime() -> None:
    dt = filetime_to_datetime(WINDOWS_EPOCH_FILETIME)
    assert dt is not None
    assert dt.tzinfo is not None
    assert snapshot_pwd_last_set(WINDOWS_EPOCH_FILETIME) == str(WINDOWS_EPOCH_FILETIME)


def test_filetime_datetime_passthrough() -> None:
    source = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    converted = filetime_to_datetime(source)
    assert converted == source


def test_compute_days_left_upcoming() -> None:
    pwd = datetime(2026, 3, 20, tzinfo=timezone.utc)
    days, expiry = compute_days_left(pwd, max_pwd_age_days=180, today=date(2026, 9, 14))
    assert expiry == date(2026, 9, 16)
    assert days == 2


def test_compute_days_left_overdue() -> None:
    pwd = datetime(2026, 1, 1, tzinfo=timezone.utc)
    days, expiry = compute_days_left(pwd, max_pwd_age_days=180, today=date(2026, 7, 10))
    assert expiry == date(2026, 6, 30)
    assert days == -10


def test_compute_days_left_must_change() -> None:
    days, expiry = compute_days_left(None, 180, today=date(2026, 1, 1))
    assert days is None
    assert expiry is None


def test_classify_user_statuses() -> None:
    assert classify_user(None, 5, must_change=True) == "must_change"
    assert classify_user(5, 5) == "upcoming"
    assert classify_user(1, 5) == "upcoming"
    assert classify_user(0, 5) == "overdue"
    assert classify_user(-3, 5) == "overdue"
    assert classify_user(30, 5) == "ok"


def test_never_expires_flag() -> None:
    uac = 512 | UAC_PASSWORD_NEVER_EXPIRES
    assert uac & UAC_PASSWORD_NEVER_EXPIRES
    assert not (512 & UAC_PASSWORD_NEVER_EXPIRES)
