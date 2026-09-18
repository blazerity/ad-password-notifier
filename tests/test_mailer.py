from pathlib import Path
from unittest.mock import MagicMock, patch

from config import SmtpConfig
from mailer import Mailer
from main import choose_run_mode


def test_dry_run_does_not_call_smtp(tmp_path: Path) -> None:
    smtp = SmtpConfig(
        host="127.0.0.1",
        port=1,
        use_tls=False,
        use_starttls=False,
        from_address="noreply@domain.local",
        username=None,
        password=None,
    )
    mailer = Mailer(smtp, dry_run=True, preview_dir=tmp_path)
    mailer.send_html(["user@domain.local"], "Требуется смена пароля", "<p>hi</p>")
    saved = list(tmp_path.glob("*.html"))
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == "<p>hi</p>"


def test_send_logs_in_then_sendmail() -> None:
    smtp = SmtpConfig(
        host="mail.example",
        port=587,
        use_tls=False,
        use_starttls=False,
        from_address="stepai@example",
        username="stepai@example",
        password="secret",
    )
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    with patch("mailer.smtplib.SMTP", return_value=client) as smtp_cls:
        Mailer(smtp).send_html(["user@example"], "Тема", "<p>hi</p>")
    smtp_cls.assert_called_once_with("mail.example", 587, timeout=30)
    client.login.assert_called_once_with("stepai@example", "secret")
    client.sendmail.assert_called_once()
    client.starttls.assert_not_called()


def test_choose_run_mode_flags() -> None:
    assert choose_run_mode(cli_dry_run=True, interactive=True) is False
    assert choose_run_mode(cli_dry_run=False, interactive=True) is True
    assert choose_run_mode(cli_dry_run=None, interactive=False) is True
