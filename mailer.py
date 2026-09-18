"""Отправка HTML-писем через smtplib и рендеринг Jinja2-шаблонов."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import PROJECT_ROOT, SmtpConfig

logger = logging.getLogger(__name__)


class MailerError(RuntimeError):
    """Ошибка SMTP-отправки."""


class Mailer:
    """Рендер шаблонов и отправка писем."""

    def __init__(
        self,
        smtp: SmtpConfig,
        templates_dir: Path | None = None,
        *,
        dry_run: bool = False,
        preview_dir: Path | None = None,
    ) -> None:
        self._smtp = smtp
        self.dry_run = dry_run
        self.preview_dir = preview_dir
        directory = templates_dir or (PROJECT_ROOT / "templates")
        self._env = Environment(
            loader=FileSystemLoader(str(directory)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_user_notification(
        self,
        *,
        full_name: str,
        username: str,
        days_left: int | None,
        expired: bool,
        instructions_url: str,
    ) -> str:
        """Собрать HTML письма пользователю."""
        days_overdue = 0 if days_left is None else max(0, -days_left)
        template = self._env.get_template("user_notification.html")
        return template.render(
            full_name=full_name,
            username=username,
            days_left=0 if days_left is None else max(days_left, 0),
            days_overdue=days_overdue,
            expired=expired,
            instructions_url=instructions_url,
        )

    def render_admin_report(self, context: dict[str, object]) -> str:
        """Собрать HTML сводного отчёта администраторам."""
        template = self._env.get_template("admin_report.html")
        return template.render(**context)

    def send_html(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
    ) -> None:
        """Отправить HTML-письмо списку получателей."""
        if not recipients:
            raise MailerError("Список получателей пуст")

        message = MIMEMultipart("alternative")
        message["From"] = self._smtp.from_address
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html", "utf-8"))

        if self.dry_run:
            self._write_preview(recipients, subject, html_body)
            logger.info("DRY-RUN: письмо не отправлено: %s -> %s", subject, ", ".join(recipients))
            return

        try:
            self._send(message, recipients)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailerError(f"Ошибка SMTP ({self._smtp.host}:{self._smtp.port}): {exc}") from exc

        logger.info("Письмо отправлено: %s -> %s", subject, ", ".join(recipients))

    def _write_preview(self, recipients: list[str], subject: str, html_body: str) -> None:
        """Сохранить HTML в data/previews при тестовом прогоне."""
        if self.preview_dir is None:
            return
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        lowered = subject.lower()
        if "отчёт" in lowered or "отчет" in lowered:
            safe = "admin_report"
        else:
            stem = recipients[0].split("@", maxsplit=1)[0] if recipients else "mail"
            safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
        path = self.preview_dir / f"{safe}.html"
        path.write_text(html_body, encoding="utf-8")
        logger.info("DRY-RUN: превью сохранено %s", path)

    def send_alert(self, recipients: list[str], error_text: str) -> None:
        """Короткое алерт-письмо о сбое выполнения скрипта."""
        body = (
            "<p>Ошибка выполнения скрипта уведомлений о сроке паролей AD.</p>"
            f"<pre style='white-space:pre-wrap'>{error_text}</pre>"
        )
        self.send_html(recipients, "Ошибка выполнения скрипта уведомлений", body)

    def _send(self, message: MIMEMultipart, recipients: list[str]) -> None:
        if self._smtp.use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._smtp.host, self._smtp.port, context=context) as client:
                self._authenticate(client)
                client.sendmail(self._smtp.from_address, recipients, message.as_string())
            return

        with smtplib.SMTP(self._smtp.host, self._smtp.port, timeout=30) as client:
            client.ehlo()
            if self._smtp.use_starttls:
                context = ssl.create_default_context()
                client.starttls(context=context)
                client.ehlo()
            self._authenticate(client)
            client.sendmail(self._smtp.from_address, recipients, message.as_string())

    def _authenticate(self, client: smtplib.SMTP) -> None:
        if self._smtp.username and self._smtp.password:
            client.login(self._smtp.username, self._smtp.password)
