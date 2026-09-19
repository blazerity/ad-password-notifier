"""Тесты сохранения ini/.env и опциональных секций schedule/web."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import ConfigError, is_user_mail_paused, load_config
from config_writer import save_ini_settings, update_env_secrets
from datetime import date

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
"""


def _write_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    ini_path.write_text(INI, encoding="utf-8")
    monkeypatch.setenv("AD_SERVICE_PASSWORD", "secret")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("WEB_PASSWORD", raising=False)
    return ini_path, env_path


def test_schedule_and_web_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path, env_path = _write_base(tmp_path, monkeypatch)
    cfg = load_config(ini_path, env_path)
    assert cfg.schedule.enabled is True
    assert cfg.schedule.cron == "0 8 * * *"
    assert cfg.schedule.pause_user_mail_until is None
    assert cfg.web.host == "127.0.0.1"
    assert cfg.web.port == 8787
    assert cfg.web.username == "admin"
    assert cfg.web.password == ""


def test_schedule_pause_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path, env_path = _write_base(tmp_path, monkeypatch)
    save_ini_settings(
        {
            "schedule": {
                "enabled": "false",
                "cron": "30 7 * * 1-5",
                "pause_user_mail_until": "2026-12-31",
            },
            "web": {"host": "0.0.0.0", "port": "9000"},
        },
        config_path=ini_path,
    )
    monkeypatch.setenv("WEB_USER", "ops")
    monkeypatch.setenv("WEB_PASSWORD", "web-secret")
    cfg = load_config(ini_path, env_path)
    assert cfg.schedule.enabled is False
    assert cfg.schedule.cron == "30 7 * * 1-5"
    assert cfg.schedule.pause_user_mail_until == date(2026, 12, 31)
    assert is_user_mail_paused(cfg, today=date(2026, 12, 31)) is True
    assert is_user_mail_paused(cfg, today=date(2027, 1, 1)) is False
    assert cfg.web.host == "0.0.0.0"
    assert cfg.web.port == 9000
    assert cfg.web.username == "ops"
    assert cfg.web.password == "web-secret"


def test_invalid_pause_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path, env_path = _write_base(tmp_path, monkeypatch)
    save_ini_settings({"schedule": {"pause_user_mail_until": "31.12.2026"}}, config_path=ini_path)
    with pytest.raises(ConfigError, match="pause_user_mail_until"):
        load_config(ini_path, env_path)


def test_update_env_secrets_preserves_empty(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("AD_SERVICE_PASSWORD=old\nWEB_USER=admin\n", encoding="utf-8")
    update_env_secrets(
        {"AD_SERVICE_PASSWORD": "", "WEB_PASSWORD": "new-pass", "WEB_USER": "admin"},
        env_path=env_path,
    )
    text = env_path.read_text(encoding="utf-8")
    assert "AD_SERVICE_PASSWORD=old" in text
    assert "WEB_PASSWORD=new-pass" in text
