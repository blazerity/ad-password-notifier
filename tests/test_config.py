"""Тесты загрузки config.ini."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import ConfigError, load_config

INI = """
[ad]
server = ldap://dc01.domain.local
domain = DOMAIN
service_user = svc_pwd_notifier
search_base = OU=Users,DC=domain,DC=local
excluded_ou = OU=Service,DC=domain,DC=local; OU=Test,DC=domain,DC=local
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
recipients = admin1@domain.local, admin2@domain.local

[logging]
log_dir = logs
file_level = DEBUG
console_level = INFO
max_log_age = 14
use_emoji = false
"""


def test_load_ini_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    ini_path.write_text(INI, encoding="utf-8")
    monkeypatch.setenv("AD_SERVICE_PASSWORD", "secret")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    cfg = load_config(ini_path, env_path)
    assert cfg.ad.server == "ldap://dc01.domain.local"
    assert cfg.ad.service_password == "secret"
    assert cfg.ad.excluded_ou == [
        "OU=Service,DC=domain,DC=local",
        "OU=Test,DC=domain,DC=local",
    ]
    assert cfg.admins.recipients == ["admin1@domain.local", "admin2@domain.local"]
    assert cfg.logging.max_log_age == 14
    assert cfg.logging.use_emoji is False
    assert cfg.smtp.use_tls is False
    assert cfg.smtp.username == "noreply@domain.local"
    assert cfg.smtp.password == "secret"


def test_smtp_env_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    ini_path.write_text(INI, encoding="utf-8")
    monkeypatch.setenv("AD_SERVICE_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_USER", "mailbox@domain.local")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")

    cfg = load_config(ini_path, env_path)
    assert cfg.smtp.username == "mailbox@domain.local"
    assert cfg.smtp.password == "smtp-secret"


def test_load_ini_requires_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ini_path = tmp_path / "config.ini"
    env_path = tmp_path / ".env"
    ini_path.write_text(INI, encoding="utf-8")
    env_path.write_text("", encoding="utf-8")
    monkeypatch.delenv("AD_SERVICE_PASSWORD", raising=False)
    with pytest.raises(ConfigError, match="AD_SERVICE_PASSWORD"):
        load_config(ini_path, env_path)
