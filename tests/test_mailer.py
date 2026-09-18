from pathlib import Path

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


def test_choose_run_mode_flags() -> None:
    assert choose_run_mode(cli_dry_run=True, interactive=True) is False
    assert choose_run_mode(cli_dry_run=False, interactive=True) is True
    assert choose_run_mode(cli_dry_run=None, interactive=False) is True
