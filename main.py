"""Точка входа: проверка сроков паролей AD и рассылка уведомлений."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from ad_client import AdClient, AdClientError, AdUser
from config import LOGGER_NAME, PROJECT_ROOT, AppConfig, load_config
from mailer import Mailer, MailerError
from notification_tracker import NotificationTracker
from report_builder import build_admin_report
from ylogger import ylog

logger = logging.getLogger(LOGGER_NAME)


def setup_logging(config: AppConfig) -> logging.Logger:
    """Подключить ylogger и продублировать обработчики на root logger."""
    app_logger = ylog(
        logger_name=LOGGER_NAME,
        log_dir=str(config.logging.log_dir),
        file_level=config.logging.file_level,
        console_level=config.logging.console_level,
        use_emoji=config.logging.use_emoji,
        max_log_age=config.logging.max_log_age,
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    for handler in app_logger.handlers:
        root.addHandler(handler)
    app_logger.propagate = False
    return app_logger


def _send_user_mail(mailer: Mailer, config: AppConfig, user: AdUser) -> None:
    expired = user.status == "overdue"
    html = mailer.render_user_notification(
        full_name=user.full_name,
        username=user.username,
        days_left=user.days_left,
        expired=expired,
        instructions_url=config.notification.instructions_url,
    )
    mailer.send_html([user.email], "🔒 Требуется смена пароля", html)


def run(config: AppConfig, today: date | None = None, *, send_emails: bool = True) -> int:
    """Выполнить полный пайплайн. Возвращает код выхода."""
    current = today or date.today()
    preview_dir = None if send_emails else (PROJECT_ROOT / "data" / "previews")
    mailer = Mailer(config.smtp, dry_run=not send_emails, preview_dir=preview_dir)
    tracker = NotificationTracker(config.notification.history_csv)
    client = AdClient(config.ad)

    if not send_emails:
        logger.info("Режим без отправки писем: SMTP выключен, история CSV не записывается")

    try:
        client.connect()
        users = client.fetch_users(config.notification.first_warning_days, today=current)
    except AdClientError as exc:
        logger.exception("Критическая ошибка Active Directory")
        _try_alert(mailer, config, str(exc), send_emails=send_emails)
        return 1
    finally:
        client.unbind()

    sent = 0
    resolved = 0
    for user in users:
        decision = tracker.decide(
            user,
            first_warning_days=config.notification.first_warning_days,
            daily_warning_threshold=config.notification.daily_warning_threshold,
            today=current,
        )
        if decision.action == "resolve" and decision.status == "resolved":
            tracker.append(user, status="resolved", today=current)
            resolved += 1
            logger.info("Цикл закрыт (пароль сменён): %s", user.username)
            decision = tracker.decide(
                user,
                first_warning_days=config.notification.first_warning_days,
                daily_warning_threshold=config.notification.daily_warning_threshold,
                today=current,
            )

        if decision.action != "send" or decision.status is None:
            logger.debug("%s: %s", user.username, decision.reason)
            continue

        try:
            _send_user_mail(mailer, config, user)
        except MailerError:
            logger.exception("Не удалось отправить письмо пользователю %s", user.username)
            continue

        tracker.append(user, status=decision.status, today=current)
        sent += 1
        logger.info(
            "%s: %s <%s> status=%s days_left=%s",
            "Будет отправлено" if not send_emails else "Уведомление отправлено",
            user.username,
            user.email,
            decision.status,
            user.days_left,
        )

    if send_emails:
        tracker.save()
    else:
        logger.info("DRY-RUN: CSV-история не сохранена")

    report = build_admin_report(
        users,
        tracker.resolved_today(current),
        first_warning_days=config.notification.first_warning_days,
        today=current,
    )
    try:
        html = mailer.render_admin_report(report.to_template_context())
        mailer.send_html(
            config.admins.recipients,
            f"📊 Отчёт по истекающим паролям — {report.report_date}",
            html,
        )
    except MailerError:
        logger.exception("Критическая ошибка SMTP при отправке отчёта администраторам")
        _try_alert(mailer, config, "Не удалось отправить сводный отчёт администраторам.", send_emails=send_emails)
        return 1

    logger.info(
        "Готово: пользователей=%s, писем=%s, закрыто циклов=%s, upcoming=%s, overdue=%s, resolved=%s",
        len(users),
        sent,
        resolved,
        len(report.upcoming),
        len(report.overdue),
        len(report.resolved),
    )
    return 0


def _try_alert(mailer: Mailer, config: AppConfig, message: str, *, send_emails: bool) -> None:
    if not send_emails:
        logger.critical("DRY-RUN: алерт не отправлен: %s", message)
        return
    try:
        mailer.send_alert(config.admins.recipients, message)
    except MailerError:
        logger.critical("SMTP недоступен, алерт не отправлен: %s", message)


def choose_run_mode(cli_dry_run: bool | None, interactive: bool) -> bool | None:
    """Вернуть True (слать письма), False (тест) или None (выход).

    Планировщик заданий (нет TTY) по умолчанию работает в боевом режиме.
    """
    if cli_dry_run is True:
        return False
    if cli_dry_run is False:
        return True
    if not interactive:
        return True

    print()
    print("AD Password Notifier")
    print("1) Боевой запуск — LDAP и отправка писем")
    print("2) Тестовый прогон — LDAP, без SMTP и без записи истории")
    print("0) Выход")
    choice = input("Выберите вариант [2]: ").strip() or "2"
    if choice == "1":
        return True
    if choice == "2":
        return False
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Уведомления об истечении паролей AD")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Тестовый прогон: без SMTP и без записи CSV",
    )
    mode.add_argument(
        "--send",
        action="store_true",
        help="Боевой запуск без меню (для Планировщика заданий)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Загрузить конфигурацию, выбрать режим и запустить пайплайн."""
    args = parse_args(argv)
    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001
        logging.basicConfig(level=logging.ERROR)
        logging.critical("Не удалось загрузить конфигурацию: %s", exc)
        return 1

    setup_logging(config)

    cli_mode: bool | None
    if args.dry_run:
        cli_mode = True
    elif args.send:
        cli_mode = False
    else:
        cli_mode = None

    send_emails = choose_run_mode(cli_dry_run=cli_mode, interactive=sys.stdin.isatty())
    if send_emails is None:
        logger.info("Выход без запуска")
        return 0

    try:
        return run(config, send_emails=send_emails)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Необработанная ошибка выполнения")
        if send_emails:
            try:
                Mailer(config.smtp).send_alert(config.admins.recipients, str(exc))
            except Exception:
                logger.critical("SMTP недоступен, алерт не отправлен: %s", exc)
        else:
            logger.critical("DRY-RUN: алерт не отправлен: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
