"""Точка входа: проверка сроков паролей AD и рассылка уведомлений."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ad_client import AdClient, AdClientError, AdUser
from config import LOGGER_NAME, PROJECT_ROOT, AppConfig, is_user_mail_paused, load_config
from mailer import Mailer, MailerError
from notification_tracker import NotificationTracker
from report_builder import build_admin_report
from report_store import RunStatus, build_stored_report, save_report, save_run_status
from run_lock import RunInProgressError, run_lock
from ylogger import ylog

logger = logging.getLogger(LOGGER_NAME)


@dataclass
class RunResult:
    """Итог одного прогона пайплайна."""

    exit_code: int
    users_count: int = 0
    sent_count: int = 0
    resolved_count: int = 0
    upcoming_count: int = 0
    overdue_count: int = 0
    user_mail_paused: bool = False
    error: str = ""


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def run(
    config: AppConfig,
    today: date | None = None,
    *,
    send_emails: bool = True,
    mode: str = "cli",
    use_lock: bool = True,
) -> int:
    """Выполнить полный пайплайн. Возвращает код выхода."""
    result = run_pipeline(
        config,
        today=today,
        send_emails=send_emails,
        mode=mode,
        use_lock=use_lock,
    )
    return result.exit_code


def run_pipeline(
    config: AppConfig,
    today: date | None = None,
    *,
    send_emails: bool = True,
    mode: str = "cli",
    use_lock: bool = True,
) -> RunResult:
    """Выполнить полный пайплайн и вернуть структурированный итог."""
    started = _now_iso()
    current = today or date.today()
    paused = is_user_mail_paused(config, current)

    def _execute() -> RunResult:
        return _run_unlocked(
            config,
            current=current,
            send_emails=send_emails,
            mode=mode,
            started=started,
            paused=paused,
        )

    try:
        if use_lock:
            with run_lock():
                return _execute()
        return _execute()
    except RunInProgressError as exc:
        logger.warning("%s", exc)
        status = RunStatus(
            started_at=started,
            finished_at=_now_iso(),
            exit_code=2,
            send_emails=send_emails,
            user_mail_paused=paused,
            users_count=0,
            sent_count=0,
            resolved_count=0,
            upcoming_count=0,
            overdue_count=0,
            error=str(exc),
            mode=mode,
        )
        save_run_status(status)
        return RunResult(exit_code=2, user_mail_paused=paused, error=str(exc))


def _run_unlocked(
    config: AppConfig,
    *,
    current: date,
    send_emails: bool,
    mode: str,
    started: str,
    paused: bool,
) -> RunResult:
    preview_dir = None if send_emails else (PROJECT_ROOT / "data" / "previews")
    mailer = Mailer(config.smtp, dry_run=not send_emails, preview_dir=preview_dir)
    tracker = NotificationTracker(config.notification.history_csv)
    client = AdClient(config.ad)

    if not send_emails:
        logger.info("Режим без отправки писем: SMTP выключен, история CSV не записывается")
    if paused and send_emails:
        logger.info(
            "Пауза пользовательских писем до %s: пользователям не отправляем",
            config.schedule.pause_user_mail_until,
        )

    try:
        client.connect()
        users = client.fetch_users(config.notification.first_warning_days, today=current)
    except AdClientError as exc:
        logger.exception("Критическая ошибка Active Directory")
        _try_alert(mailer, config, str(exc), send_emails=send_emails)
        result = RunResult(exit_code=1, user_mail_paused=paused, error=str(exc))
        _persist_status(result, send_emails=send_emails, mode=mode, started=started)
        return result
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

        if paused and send_emails:
            logger.info("%s: пропуск письма (пауза рассылки)", user.username)
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
    stored = build_stored_report(report, users, source=mode)
    save_report(stored)

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
        result = RunResult(
            exit_code=1,
            users_count=len(users),
            sent_count=sent,
            resolved_count=resolved,
            upcoming_count=len(report.upcoming),
            overdue_count=len(report.overdue),
            user_mail_paused=paused,
            error="Не удалось отправить сводный отчёт администраторам.",
        )
        _persist_status(result, send_emails=send_emails, mode=mode, started=started)
        return result

    logger.info(
        "Готово: пользователей=%s, писем=%s, закрыто циклов=%s, upcoming=%s, overdue=%s, resolved=%s",
        len(users),
        sent,
        resolved,
        len(report.upcoming),
        len(report.overdue),
        len(report.resolved),
    )
    result = RunResult(
        exit_code=0,
        users_count=len(users),
        sent_count=sent,
        resolved_count=resolved,
        upcoming_count=len(report.upcoming),
        overdue_count=len(report.overdue),
        user_mail_paused=paused,
    )
    _persist_status(result, send_emails=send_emails, mode=mode, started=started)
    return result


def _persist_status(
    result: RunResult,
    *,
    send_emails: bool,
    mode: str,
    started: str,
) -> None:
    save_run_status(
        RunStatus(
            started_at=started,
            finished_at=_now_iso(),
            exit_code=result.exit_code,
            send_emails=send_emails,
            user_mail_paused=result.user_mail_paused,
            users_count=result.users_count,
            sent_count=result.sent_count,
            resolved_count=result.resolved_count,
            upcoming_count=result.upcoming_count,
            overdue_count=result.overdue_count,
            error=result.error,
            mode=mode,
        )
    )


def notify_users_now(
    config: AppConfig,
    usernames: list[str],
    *,
    today: date | None = None,
    send_emails: bool = True,
) -> RunResult:
    """Принудительно отправить напоминание выбранным пользователям."""
    current = today or date.today()
    wanted = {name.lower() for name in usernames if name.strip()}
    if not wanted:
        return RunResult(exit_code=1, error="Не выбраны пользователи")

    started = _now_iso()
    preview_dir = None if send_emails else (PROJECT_ROOT / "data" / "previews")
    mailer = Mailer(config.smtp, dry_run=not send_emails, preview_dir=preview_dir)
    tracker = NotificationTracker(config.notification.history_csv)
    client = AdClient(config.ad)

    try:
        with run_lock():
            try:
                client.connect()
                users = client.fetch_users(config.notification.first_warning_days, today=current)
            except AdClientError as exc:
                logger.exception("AD недоступен при ручной рассылке")
                return RunResult(exit_code=1, error=str(exc))
            finally:
                client.unbind()

            matched = [user for user in users if user.username.lower() in wanted]
            if not matched:
                return RunResult(exit_code=1, error="Выбранные пользователи не найдены в AD")

            sent = 0
            for user in matched:
                if user.status == "must_change":
                    logger.info("%s: must_change, ручное письмо пропущено", user.username)
                    continue
                if tracker.already_sent_today(user.username, current) and send_emails:
                    logger.info("%s: уже уведомлён сегодня", user.username)
                    continue
                status = "overdue" if user.status == "overdue" else "upcoming"
                try:
                    _send_user_mail(mailer, config, user)
                except MailerError as exc:
                    logger.exception("Ручная отправка не удалась: %s", user.username)
                    return RunResult(exit_code=1, sent_count=sent, error=str(exc))
                if send_emails:
                    tracker.append(user, status=status, today=current)
                sent += 1

            if send_emails:
                tracker.save()

            report = build_admin_report(
                users,
                tracker.resolved_today(current),
                first_warning_days=config.notification.first_warning_days,
                today=current,
            )
            save_report(build_stored_report(report, users, source="manual"))
            result = RunResult(
                exit_code=0,
                users_count=len(matched),
                sent_count=sent,
                upcoming_count=len(report.upcoming),
                overdue_count=len(report.overdue),
            )
            _persist_status(result, send_emails=send_emails, mode="manual", started=started)
            return result
    except RunInProgressError as exc:
        return RunResult(exit_code=2, error=str(exc))


def test_ad_connection(config: AppConfig) -> str:
    """Проверить LDAP-подключение. Возвращает сообщение об успехе или бросает AdClientError."""
    client = AdClient(config.ad)
    try:
        client.connect()
        return f"AD OK: {config.ad.server} ({config.ad.domain}\\{config.ad.service_user})"
    finally:
        client.unbind()


def test_smtp_connection(config: AppConfig) -> str:
    """Проверить SMTP (EHLO + AUTH без отправки письма)."""
    import smtplib
    import ssl

    smtp = config.smtp
    try:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as client:
            client.ehlo()
            if smtp.use_tls or smtp.use_starttls:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if smtp.username:
                client.login(smtp.username, smtp.password or "")
        return f"SMTP OK: {smtp.host}:{smtp.port}"
    except (OSError, smtplib.SMTPException) as exc:
        raise MailerError(f"SMTP недоступен ({smtp.host}:{smtp.port}): {exc}") from exc


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
    mode.add_argument(
        "--serve",
        action="store_true",
        help="Запустить web-интерфейс и планировщик (режим службы)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Загрузить конфигурацию, выбрать режим и запустить пайплайн."""
    args = parse_args(argv)

    if args.serve:
        from service_main import serve

        return serve()

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
        return run(config, send_emails=send_emails, mode="cli")
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
