"""CLI-точка входа: консольный прогон или режим службы (--serve)."""

from __future__ import annotations

import argparse
import logging
import sys

from config import load_config
from mailer import Mailer
from pipeline import run, setup_logging

logger = logging.getLogger(__name__)


def choose_run_mode(cli_dry_run: bool | None, interactive: bool) -> bool | None:
    """Вернуть True (слать письма), False (тест) или None (выход).

    Без TTY (cron/systemd oneshot) по умолчанию — боевой режим.
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
        help="Боевой запуск без меню (для cron)",
    )
    mode.add_argument(
        "--serve",
        action="store_true",
        help="Запустить web-интерфейс и планировщик (режим systemd-службы)",
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
