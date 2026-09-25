"""LDAP-клиент Active Directory: выборка пользователей и расчёт срока пароля."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from ldap3 import ALL, BASE, NTLM, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException

from config import AdConfig, AppConfig

logger = logging.getLogger(__name__)

UAC_ACCOUNTDISABLE = 0x0002
UAC_PASSWORD_NEVER_EXPIRES = 0x10000
WINDOWS_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

UserStatus = Literal["ok", "upcoming", "overdue", "must_change"]

LDAP_USER_FILTER = (
    "(&(objectCategory=person)(objectClass=user)"
    f"(!(userAccountControl:1.2.840.113556.1.4.803:={UAC_ACCOUNTDISABLE})))"
)
LDAP_ATTRIBUTES = [
    "sAMAccountName",
    "displayName",
    "cn",
    "mail",
    "pwdLastSet",
    "userAccountControl",
    "distinguishedName",
]


class AdClientError(RuntimeError):
    """Ошибка подключения или поиска в Active Directory."""


@dataclass
class AdUser:
    """Пользователь AD с рассчитанным сроком пароля."""

    username: str
    email: str
    full_name: str
    distinguished_name: str
    user_account_control: int
    pwd_last_set: datetime | None
    pwd_last_set_snapshot: str
    days_left: int | None
    expiry_date: date | None
    status: UserStatus


def filetime_to_datetime(value: Any) -> datetime | None:
    """Преобразовать Windows FILETIME / ldap3 datetime в timezone-aware datetime.

    0 или None означают «пароль не задан / требуется смена при входе».
    """
    if value in (None, 0, "0"):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return filetime_to_datetime(value[0])
    try:
        raw = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Некорректный pwdLastSet: {value!r}") from exc
    if raw == 0:
        return None
    return WINDOWS_EPOCH + timedelta(microseconds=raw / 10)


def snapshot_pwd_last_set(value: Any) -> str:
    """Стабильный снимок pwdLastSet для сравнения циклов уведомлений."""
    if value in (None, 0, "0"):
        return "0"
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return str(int((dt.astimezone(timezone.utc) - WINDOWS_EPOCH).total_seconds() * 10_000_000))
    if isinstance(value, (list, tuple)):
        return snapshot_pwd_last_set(value[0] if value else 0)
    return str(int(value))


def compute_days_left(
    pwd_last_set: datetime | None,
    max_pwd_age_days: int,
    today: date | None = None,
) -> tuple[int | None, date | None]:
    """Вернуть (days_left, expiry_date). None, если требуется смена при входе."""
    if pwd_last_set is None:
        return None, None
    current = today or date.today()
    expiry = pwd_last_set.date() + timedelta(days=max_pwd_age_days)
    return (expiry - current).days, expiry


def classify_user(
    days_left: int | None,
    first_warning_days: int,
    *,
    must_change: bool = False,
) -> UserStatus:
    """Классифицировать учётную запись по оставшимся дням срока пароля."""
    if must_change or days_left is None:
        return "must_change"
    if days_left <= 0:
        return "overdue"
    if days_left <= first_warning_days:
        return "upcoming"
    return "ok"


def _first_value(values: Any, default: Any = None) -> Any:
    if values in (None, "", []):
        return default
    if isinstance(values, (list, tuple)):
        return values[0] if values else default
    return values


def _is_excluded(dn: str, excluded_ou: list[str]) -> bool:
    dn_upper = dn.upper()
    return any(fragment.upper() in dn_upper for fragment in excluded_ou if fragment)


class AdClient:
    """Подключение к AD и выборка активных пользователей с email."""

    def __init__(self, ad_config: AdConfig) -> None:
        self._config = ad_config
        self._connection: Connection | None = None

    def connect(self) -> Connection:
        """Открыть LDAP-сессию от имени сервисной учётки (NTLM)."""
        try:
            use_ssl = self._config.server.lower().startswith("ldaps://")
            server = Server(self._config.server, get_info=ALL, use_ssl=use_ssl)
            user = f"{self._config.domain}\\{self._config.service_user}"
            connection = Connection(
                server,
                user=user,
                password=self._config.service_password,
                authentication=NTLM,
                auto_bind=True,
                raise_exceptions=True,
            )
        except (LDAPException, ValueError, ModuleNotFoundError) as exc:
            raise AdClientError(f"Не удалось подключиться к AD: {exc}") from exc

        self._connection = connection
        logger.info("Подключение к AD установлено: %s (%s)", self._config.server, user)
        return connection

    def unbind(self) -> None:
        """Закрыть LDAP-соединение."""
        if self._connection and self._connection.bound:
            self._connection.unbind()
            logger.info("Соединение с AD закрыто")
        self._connection = None

    def verify_search_access(self) -> str:
        """Проверить, что УЗ может читать search_base (BASE-поиск).

        Возвращает DN найденного объекта или бросает AdClientError.
        """
        if self._connection is None or not self._connection.bound:
            raise AdClientError("Сначала вызовите connect()")

        try:
            ok = self._connection.search(
                search_base=self._config.search_base,
                search_filter="(objectClass=*)",
                search_scope=BASE,
                attributes=["distinguishedName"],
                size_limit=1,
            )
        except LDAPException as exc:
            raise AdClientError(
                f"Нет доступа к search_base «{self._config.search_base}»: {exc}"
            ) from exc

        if not ok or not self._connection.entries:
            raise AdClientError(
                f"Нет доступа к search_base «{self._config.search_base}»: "
                "объект не найден или недостаточно прав"
            )
        dn = str(self._connection.entries[0].entry_dn)
        logger.info("Доступ к search_base подтверждён: %s", dn)
        return dn

    def fetch_users(
        self,
        first_warning_days: int,
        today: date | None = None,
    ) -> list[AdUser]:
        """Выгрузить пользователей из search_base и рассчитать срок пароля."""
        if self._connection is None or not self._connection.bound:
            raise AdClientError("Сначала вызовите connect()")

        try:
            entries = self._connection.extend.standard.paged_search(
                search_base=self._config.search_base,
                search_filter=LDAP_USER_FILTER,
                search_scope=SUBTREE,
                attributes=LDAP_ATTRIBUTES,
                paged_size=500,
                generator=False,
            )
        except LDAPException as exc:
            raise AdClientError(f"Ошибка LDAP-поиска: {exc}") from exc

        users: list[AdUser] = []
        skipped_no_mail = 0
        skipped_never_expires = 0
        skipped_excluded = 0

        for entry in entries:
            if entry.get("type") not in (None, "searchResEntry"):
                continue
            attrs = entry.get("attributes") or {}
            dn = str(entry.get("dn") or "")
            username = str(_first_value(attrs.get("sAMAccountName"), "") or "")
            if _is_excluded(dn, self._config.excluded_ou):
                skipped_excluded += 1
                logger.info("Пропущен %s: исключённый OU", username or dn)
                continue

            uac = int(_first_value(attrs.get("userAccountControl"), 0) or 0)
            if uac & UAC_PASSWORD_NEVER_EXPIRES:
                skipped_never_expires += 1
                logger.warning("Пропущен %s: PASSWORD_NEVER_EXPIRES", username or dn)
                continue

            mail = str(_first_value(attrs.get("mail"), "") or "").strip()
            if not mail:
                skipped_no_mail += 1
                logger.warning("Пропущен %s: нет email", username or dn)
                continue

            raw_pwd = _first_value(attrs.get("pwdLastSet"), 0)
            pwd_dt = filetime_to_datetime(raw_pwd)
            days_left, expiry = compute_days_left(
                pwd_dt, self._config.max_pwd_age_days, today=today
            )
            status = classify_user(
                days_left,
                first_warning_days,
                must_change=pwd_dt is None,
            )
            full_name = str(
                _first_value(attrs.get("displayName"))
                or _first_value(attrs.get("cn"))
                or username
            )

            users.append(
                AdUser(
                    username=username,
                    email=mail,
                    full_name=full_name,
                    distinguished_name=dn,
                    user_account_control=uac,
                    pwd_last_set=pwd_dt,
                    pwd_last_set_snapshot=snapshot_pwd_last_set(raw_pwd),
                    days_left=days_left,
                    expiry_date=expiry,
                    status=status,
                )
            )

        logger.info(
            "Обработано пользователей: %s (пропущено без email: %s, never-expires: %s, OU: %s)",
            len(users),
            skipped_no_mail,
            skipped_never_expires,
            skipped_excluded,
        )
        return users


def test_ad_connection(
    config: AppConfig,
    *,
    server: str | None = None,
    domain: str | None = None,
    service_user: str | None = None,
    service_password: str | None = None,
    search_base: str | None = None,
) -> str:
    """Проверить LDAP-соединение и доступ УЗ к search_base.

    Непустые override-параметры подставляются вместо значений из config
    (удобно проверить поля формы до сохранения). Пустой пароль → из config.
    """
    ad = config.ad
    overrides: dict[str, object] = {}
    if server and server.strip():
        overrides["server"] = server.strip()
    if domain and domain.strip():
        overrides["domain"] = domain.strip()
    if service_user and service_user.strip():
        overrides["service_user"] = service_user.strip()
    if service_password:
        overrides["service_password"] = service_password
    if search_base and search_base.strip():
        overrides["search_base"] = search_base.strip()
    if overrides:
        ad = replace(ad, **overrides)

    if not ad.service_password:
        raise AdClientError(
            "Не задан пароль сервисной УЗ (укажите в форме или AD_SERVICE_PASSWORD в .env)"
        )
    if not ad.server or not ad.service_user or not ad.search_base:
        raise AdClientError("Укажите сервер, учётную запись и search_base")

    client = AdClient(ad)
    try:
        client.connect()
        dn = client.verify_search_access()
        return (
            f"AD OK: соединение и доступ подтверждены — "
            f"{ad.server} ({ad.domain}\\{ad.service_user}), search_base={dn}"
        )
    finally:
        client.unbind()
