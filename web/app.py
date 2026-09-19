"""Встроенный web-интерфейс администратора (FastAPI + Jinja2)."""

from __future__ import annotations

import logging
import secrets
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ad_client import AdClientError
from config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_ENV_PATH,
    AppConfig,
    ConfigError,
    is_user_mail_paused,
    load_config,
)
from config_writer import relative_to_project, save_ini_settings, update_env_secrets
from mailer import MailerError
from main import notify_users_now, run_pipeline, setup_logging, test_ad_connection, test_smtp_connection
from report_store import load_report, load_run_status

logger = logging.getLogger(__name__)

WEB_ROOT = Path(__file__).resolve().parent
security = HTTPBasic(auto_error=False)


def create_app(
    *,
    get_config: Callable[[], AppConfig] | None = None,
    reload_config: Callable[[], AppConfig] | None = None,
    config_path: Path | None = None,
    env_path: Path | None = None,
) -> FastAPI:
    """Фабрика FastAPI-приложения."""

    state: dict[str, Any] = {
        "config": None,
        "flash": None,
    }

    def _load() -> AppConfig:
        cfg = load_config(config_path or DEFAULT_CONFIG_PATH, env_path or DEFAULT_ENV_PATH)
        state["config"] = cfg
        return cfg

    get_cfg = get_config or (lambda: state["config"] or _load())
    do_reload = reload_config or _load

    app = FastAPI(title="AD Password Notifier", docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_hex(16),
        same_site="lax",
        https_only=False,
    )
    templates = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
    static_dir = WEB_ROOT / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def require_auth(
        credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    ) -> None:
        cfg = get_cfg()
        if not cfg.web.password:
            return
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется вход",
                headers={"WWW-Authenticate": "Basic"},
            )
        user_ok = secrets.compare_digest(credentials.username, cfg.web.username)
        pass_ok = secrets.compare_digest(credentials.password, cfg.web.password)
        if not (user_ok and pass_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный логин или пароль",
                headers={"WWW-Authenticate": "Basic"},
            )

    def _flash(request: Request, message: str, level: str = "info") -> None:
        request.session["flash"] = {"message": message, "level": level}

    def _pop_flash(request: Request) -> dict[str, str] | None:
        return request.session.pop("flash", None)

    def _base_ctx(request: Request, **extra: Any) -> dict[str, Any]:
        cfg = get_cfg()
        return {
            "request": request,
            "flash": _pop_flash(request),
            "config": cfg,
            "paused": is_user_mail_paused(cfg),
            "auth_enabled": bool(cfg.web.password),
            **extra,
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
        report = load_report()
        status_info = load_run_status()
        q = (request.query_params.get("q") or "").strip().lower()
        section = (request.query_params.get("section") or "attention").strip()

        rows = []
        if report:
            if section == "upcoming":
                rows = report.upcoming
            elif section == "overdue":
                rows = report.overdue
            elif section == "resolved":
                rows = report.resolved
            elif section == "all":
                rows = report.all_users
            else:
                rows = list(report.overdue) + list(report.upcoming)
            if q:
                rows = [
                    row
                    for row in rows
                    if q in row.username.lower()
                    or q in row.full_name.lower()
                    or q in row.email.lower()
                ]

        return templates.TemplateResponse(
            request,
            "dashboard.html",
            _base_ctx(
                request,
                report=report,
                status=status_info,
                rows=rows,
                q=q,
                section=section,
            ),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
        cfg = get_cfg()
        return templates.TemplateResponse(
            request,
            "settings.html",
            _base_ctx(
                request,
                history_csv_display=relative_to_project(cfg.notification.history_csv),
                log_dir_display=relative_to_project(cfg.logging.log_dir),
            ),
        )

    @app.post("/settings")
    def settings_save(
        request: Request,
        _: None = Depends(require_auth),
        ad_server: str = Form(""),
        ad_domain: str = Form(""),
        ad_service_user: str = Form(""),
        ad_search_base: str = Form(""),
        ad_excluded_ou: str = Form(""),
        ad_max_pwd_age_days: str = Form("180"),
        first_warning_days: str = Form("5"),
        daily_warning_threshold: str = Form("3"),
        history_csv: str = Form("data/notification_history.csv"),
        instructions_url: str = Form(""),
        smtp_host: str = Form(""),
        smtp_port: str = Form("25"),
        smtp_use_tls: str = Form(""),
        smtp_use_starttls: str = Form(""),
        smtp_from_address: str = Form(""),
        admins_recipients: str = Form(""),
        log_dir: str = Form("logs"),
        file_level: str = Form("DEBUG"),
        console_level: str = Form("INFO"),
        max_log_age: str = Form("30"),
        use_emoji: str = Form(""),
        schedule_enabled: str = Form(""),
        schedule_cron: str = Form("0 8 * * *"),
        pause_user_mail_until: str = Form(""),
        web_host: str = Form("127.0.0.1"),
        web_port: str = Form("8787"),
        ad_service_password: str = Form(""),
        smtp_user: str = Form(""),
        smtp_password: str = Form(""),
        web_user: str = Form(""),
        web_password: str = Form(""),
    ) -> RedirectResponse:
        try:
            save_ini_settings(
                {
                    "ad": {
                        "server": ad_server.strip(),
                        "domain": ad_domain.strip(),
                        "service_user": ad_service_user.strip(),
                        "search_base": ad_search_base.strip(),
                        "excluded_ou": ad_excluded_ou.strip(),
                        "max_pwd_age_days": ad_max_pwd_age_days.strip(),
                    },
                    "notification": {
                        "first_warning_days": first_warning_days.strip(),
                        "daily_warning_threshold": daily_warning_threshold.strip(),
                        "history_csv": history_csv.strip() or "data/notification_history.csv",
                        "instructions_url": instructions_url.strip(),
                    },
                    "smtp": {
                        "host": smtp_host.strip(),
                        "port": smtp_port.strip(),
                        "use_tls": "true" if smtp_use_tls else "false",
                        "use_starttls": "true" if smtp_use_starttls else "false",
                        "from_address": smtp_from_address.strip(),
                    },
                    "admins": {
                        "recipients": admins_recipients.strip(),
                    },
                    "logging": {
                        "log_dir": log_dir.strip() or "logs",
                        "file_level": file_level.strip() or "DEBUG",
                        "console_level": console_level.strip() or "INFO",
                        "max_log_age": max_log_age.strip() or "30",
                        "use_emoji": "true" if use_emoji else "false",
                    },
                    "schedule": {
                        "enabled": "true" if schedule_enabled else "false",
                        "cron": schedule_cron.strip() or "0 8 * * *",
                        "pause_user_mail_until": pause_user_mail_until.strip(),
                    },
                    "web": {
                        "host": web_host.strip() or "127.0.0.1",
                        "port": web_port.strip() or "8787",
                    },
                },
                config_path=config_path or DEFAULT_CONFIG_PATH,
            )
            update_env_secrets(
                {
                    "AD_SERVICE_PASSWORD": ad_service_password,
                    "SMTP_USER": smtp_user,
                    "SMTP_PASSWORD": smtp_password,
                    "WEB_USER": web_user,
                    "WEB_PASSWORD": web_password,
                },
                env_path=env_path or DEFAULT_ENV_PATH,
            )
            do_reload()
            _flash(request, "Настройки сохранены. Перезапуск службы нужен только при смене host/port web.", "ok")
        except (ConfigError, OSError, ValueError) as exc:
            logger.exception("Ошибка сохранения настроек")
            _flash(request, f"Не удалось сохранить: {exc}", "error")
        return RedirectResponse(url="/settings", status_code=303)

    @app.post("/actions/run")
    def action_run(
        request: Request,
        _: None = Depends(require_auth),
        dry_run: str = Form(""),
    ) -> RedirectResponse:
        cfg = get_cfg()
        send_emails = not bool(dry_run)
        try:
            result = run_pipeline(
                cfg,
                send_emails=send_emails,
                mode="web-dry-run" if dry_run else "web",
            )
            if result.exit_code == 0:
                label = "тестовый прогон" if dry_run else "боевой прогон"
                _flash(
                    request,
                    f"Готово ({label}): пользователей={result.users_count}, писем={result.sent_count}, "
                    f"upcoming={result.upcoming_count}, overdue={result.overdue_count}",
                    "ok",
                )
            else:
                _flash(request, result.error or f"Прогон завершился с кодом {result.exit_code}", "error")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка прогона из web")
            _flash(request, str(exc), "error")
        return RedirectResponse(url="/", status_code=303)

    @app.post("/actions/notify")
    async def action_notify(request: Request, _: None = Depends(require_auth)) -> RedirectResponse:
        form = await request.form()
        usernames = [str(v) for v in form.getlist("usernames")]
        cfg = get_cfg()
        try:
            result = notify_users_now(cfg, usernames, send_emails=True)
            if result.exit_code == 0:
                _flash(request, f"Отправлено напоминаний: {result.sent_count}", "ok")
            else:
                _flash(request, result.error or "Не удалось отправить", "error")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка ручной рассылки")
            _flash(request, str(exc), "error")
        return RedirectResponse(url="/", status_code=303)

    @app.post("/actions/test-ad")
    def action_test_ad(request: Request, _: None = Depends(require_auth)) -> RedirectResponse:
        try:
            msg = test_ad_connection(get_cfg())
            _flash(request, msg, "ok")
        except AdClientError as exc:
            _flash(request, str(exc), "error")
        return RedirectResponse(url="/settings", status_code=303)

    @app.post("/actions/test-smtp")
    def action_test_smtp(request: Request, _: None = Depends(require_auth)) -> RedirectResponse:
        try:
            msg = test_smtp_connection(get_cfg())
            _flash(request, msg, "ok")
        except MailerError as exc:
            _flash(request, str(exc), "error")
        return RedirectResponse(url="/settings", status_code=303)

    @app.post("/actions/pause")
    def action_pause(
        request: Request,
        _: None = Depends(require_auth),
        until: str = Form(""),
        clear: str = Form(""),
    ) -> RedirectResponse:
        value = "" if clear else until.strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                _flash(request, "Дата паузы должна быть в формате YYYY-MM-DD", "error")
                return RedirectResponse(url="/", status_code=303)
        try:
            save_ini_settings(
                {"schedule": {"pause_user_mail_until": value}},
                config_path=config_path or DEFAULT_CONFIG_PATH,
            )
            do_reload()
            if value:
                _flash(request, f"Пауза пользовательских писем до {value}", "ok")
            else:
                _flash(request, "Пауза рассылки снята", "ok")
        except (ConfigError, OSError) as exc:
            _flash(request, str(exc), "error")
        return RedirectResponse(url="/", status_code=303)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    try:
        do_reload()
        setup_logging(get_cfg())
    except ConfigError:
        logger.warning("Конфиг ещё не готов при старте web")

    return app
