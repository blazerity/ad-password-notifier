"""Фабрики тестовых объектов."""

from datetime import date, datetime, timezone

from ad_client import AdUser, UserStatus


def make_user(
    *,
    username: str = "jdoe",
    email: str = "jdoe@domain.local",
    full_name: str = "John Doe",
    days_left: int | None = 5,
    status: UserStatus = "upcoming",
    snapshot: str = "111",
    pwd_last_set: datetime | None = None,
) -> AdUser:
    expiry = None
    pwd = pwd_last_set
    if days_left is not None:
        expiry = date.today()
        pwd = pwd or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return AdUser(
        username=username,
        email=email,
        full_name=full_name,
        distinguished_name=f"CN={username},OU=Users,DC=domain,DC=local",
        user_account_control=512,
        pwd_last_set=pwd,
        pwd_last_set_snapshot=snapshot,
        days_left=days_left,
        expiry_date=expiry,
        status=status,
    )
