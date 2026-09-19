"""Тесты паузы пользовательских писем в пайплайне."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import load_config
from main import run_pipeline
from tests.factories import make_user

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
pause_user_mail_until = 2026-09-19
"""


def test_pause_skips_user_mail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    history = tmp_path / "history.csv"
    ini = INI.replace("data/notification_history.csv", str(history).replace("\\", "/"))
    ini = ini.replace("log_dir = logs", f"log_dir = {tmp_path / 'logs'}".replace("\\", "/"))
    ini_path.write_text(ini, encoding="utf-8")
    monkeypatch.setenv("AD_SERVICE_PASSWORD", "secret")

    cfg = load_config(ini_path, env_path)
    user = make_user(username="jdoe", days_left=2, status="upcoming")

    mock_client = MagicMock()
    mock_client.fetch_users.return_value = [user]
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("main.AdClient", return_value=mock_client),
        patch("main.Mailer") as mailer_cls,
        patch("main.save_report"),
        patch("main.save_run_status"),
        patch("main.run_lock"),
    ):
        mailer = mailer_cls.return_value
        mailer.render_admin_report.return_value = "<html></html>"
        mailer.render_user_notification.return_value = "<html></html>"
        result = run_pipeline(
            cfg,
            today=date(2026, 9, 19),
            send_emails=True,
            mode="test",
            use_lock=False,
        )

    assert result.exit_code == 0
    assert result.user_mail_paused is True
    assert result.sent_count == 0
    mailer.send_html.assert_called()  # админ-отчёт всё равно уходит
    # user notification не рендерили
    mailer.render_user_notification.assert_not_called()
