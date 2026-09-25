"""Тесты web UI на TestClient без живого AD."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import load_config
from report_builder import build_admin_report
from report_store import build_stored_report, save_report
from tests.factories import make_user
from web.app import create_app

INI = """
[ad]
server = ldap://dc01.domain.local
domain = DOMAIN
service_user = svc_pwd_notifier
search_base = OU=Users,DC=domain,DC=local
excluded_ou =
max_pwd_age_days = 180

[notification]
first_warning_days = 5
daily_warning_threshold = 3
history_csv = data/notification_history.csv
instructions_url = https://intranet.example.local/pwd

[smtp]
host = mail.domain.local
port = 25
use_tls = false
use_starttls = false
from_address = noreply@domain.local

[admins]
recipients = admin1@domain.local

[logging]
log_dir = logs
file_level = DEBUG
console_level = INFO
max_log_age = 14
use_emoji = false

[schedule]
enabled = true
cron = 0 8 * * *
pause_user_mail_until =

[web]
host = 127.0.0.1
port = 8787
"""


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    ini_path.write_text(INI, encoding="utf-8")
    env_path.write_text("AD_SERVICE_PASSWORD=secret\nWEB_PASSWORD=webpass\n", encoding="utf-8")
    monkeypatch.setenv("AD_SERVICE_PASSWORD", "secret")
    monkeypatch.setenv("WEB_USER", "admin")
    monkeypatch.setenv("WEB_PASSWORD", "webpass")

    # отчёт в стандартном пути — подменим через monkeypatch путей report_store
    report_path = tmp_path / "last_report.json"
    users = [make_user(username="jdoe", days_left=2, status="upcoming")]
    report = build_admin_report(users, [], first_warning_days=5)
    save_report(build_stored_report(report, users), report_path)

    monkeypatch.setattr("web.app.load_report", lambda: __import__("report_store", fromlist=["load_report"]).load_report(report_path))
    monkeypatch.setattr("web.app.load_run_status", lambda: None)

    app = create_app(config_path=ini_path, env_path=env_path)
    return TestClient(app)


def test_dashboard_requires_auth(client: TestClient) -> None:
    response = client.get("/", auth=("admin", "wrong"))
    assert response.status_code == 401


def test_dashboard_ok(client: TestClient) -> None:
    response = client.get("/", auth=("admin", "webpass"))
    assert response.status_code == 200
    assert "AD Password Notifier" in response.text
    assert "jdoe" in response.text


def test_settings_page(client: TestClient) -> None:
    response = client.get("/settings", auth=("admin", "webpass"))
    assert response.status_code == 200
    assert "Active Directory" in response.text
    assert "ldap://dc01.domain.local" in response.text
    assert "Проверить соединение и доступ к AD" in response.text
    assert 'formaction="/actions/test-ad"' in response.text


def test_test_ad_uses_form_overrides(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_test_ad(
        config,
        *,
        server=None,
        domain=None,
        service_user=None,
        service_password=None,
        search_base=None,
    ):
        captured.update(
            {
                "server": server,
                "domain": domain,
                "service_user": service_user,
                "service_password": service_password,
                "search_base": search_base,
            }
        )
        return "AD OK: test"

    monkeypatch.setattr("web.app.test_ad_connection", fake_test_ad)
    response = client.post(
        "/actions/test-ad",
        data={
            "ad_server": "ldaps://dc02.domain.local",
            "ad_domain": "CORP",
            "ad_service_user": "svc_check",
            "ad_service_password": "temp-secret",
            "ad_search_base": "OU=Staff,DC=domain,DC=local",
        },
        auth=("admin", "webpass"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings"
    assert captured["server"] == "ldaps://dc02.domain.local"
    assert captured["domain"] == "CORP"
    assert captured["service_user"] == "svc_check"
    assert captured["service_password"] == "temp-secret"
    assert captured["search_base"] == "OU=Staff,DC=domain,DC=local"


def test_health(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
