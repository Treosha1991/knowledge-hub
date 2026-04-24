from __future__ import annotations

from pathlib import Path

from .mail import get_smtp_status
from .ownership import DEFAULT_OWNER_EMAIL
from .public_urls import get_public_base_url
from ..utils import is_local_base_url


def build_deploy_readiness(config) -> dict:
    root_dir = Path(config.get("ROOT_DIR", Path.cwd()))
    env_name = str(config.get("ENV_NAME", "development")).strip().lower()
    data_dir = Path(config["DATA_DIR"])
    exports_dir = Path(config["PROJECT_EXPORTS_DIR"])
    backups_dir = Path(config["BACKUPS_DIR"])
    mail_outbox_dir = Path(config["MAIL_OUTBOX_DIR"])
    database_url = str(config.get("DATABASE_URL", "")).strip()
    secret_key = str(config.get("SECRET_KEY", ""))
    default_owner_email = str(config.get("DEFAULT_OWNER_EMAIL", DEFAULT_OWNER_EMAIL)).strip().lower()
    mail_backend = str(config.get("MAIL_BACKEND", "file")).strip().lower()
    mail_from_address = str(config.get("MAIL_FROM_ADDRESS", "")).strip().lower()
    public_base_url = get_public_base_url(config)
    smtp_status = get_smtp_status(config)
    auth_required_enabled = bool(config.get("AUTH_REQUIRED", False))
    is_production = env_name == "production"
    secure_cookies_ready = bool(config.get("SESSION_COOKIE_SECURE"))
    proxy_trust_ready = bool(config.get("TRUST_PROXY"))

    checks = [
        _check(
            "environment",
            "Production mode",
            "pass" if is_production else "warn",
            "Running in production mode." if is_production else "Still running in development mode.",
        ),
        _check(
            "secret_key",
            "Secret key",
            "pass" if secret_key and secret_key != "knowledge-hub-dev-key" and len(secret_key) >= 16 else "fail",
            (
                "Secret key looks production-safe."
                if secret_key and secret_key != "knowledge-hub-dev-key" and len(secret_key) >= 16
                else "Secret key is still default or too short."
            ),
        ),
        _check(
            "https_cookies",
            "Secure cookies",
            "pass" if not is_production or secure_cookies_ready else "fail",
            "Session cookies are secure for production."
            if is_production and secure_cookies_ready
            else "Secure cookies are not required yet outside production."
            if not is_production
            else "Production mode needs SESSION_COOKIE_SECURE enabled.",
        ),
        _check(
            "proxy",
            "Proxy trust",
            "pass" if not is_production or proxy_trust_ready else "warn",
            "Proxy headers are trusted."
            if is_production and proxy_trust_ready
            else "Proxy trust is not required yet outside production."
            if not is_production
            else "Production usually needs TRUST_PROXY behind Render or another reverse proxy.",
        ),
        _check(
            "auth_gate",
            "Authentication gate",
            "pass" if auth_required_enabled else "warn" if not is_production else "fail",
            (
                "Authentication gate is enabled."
                if auth_required_enabled
                else "Knowledge Hub still allows the default-owner fallback. Set KH_AUTH_REQUIRED=1 before production."
            ),
        ),
        _build_public_base_url_check(public_base_url, is_production),
        _check(
            "wsgi",
            "WSGI entrypoint",
            "pass" if (root_dir / "wsgi.py").exists() else "fail",
            "wsgi.py is present." if (root_dir / "wsgi.py").exists() else "wsgi.py is missing.",
        ),
        _check(
            "render_blueprint",
            "Render blueprint",
            "pass" if (root_dir / "render.yaml").exists() else "warn",
            "render.yaml is present." if (root_dir / "render.yaml").exists() else "render.yaml is missing.",
        ),
        _check(
            "data_dir",
            "Persistent data directory",
            "pass" if _is_writable_directory(data_dir) else "fail",
            f"Data directory is writable: {data_dir}" if _is_writable_directory(data_dir) else f"Data directory is not writable: {data_dir}",
        ),
        _build_database_check(database_url, data_dir),
        _check(
            "exports_dir",
            "Exports directory",
            "pass" if _is_writable_directory(exports_dir) else "fail",
            f"Exports directory is writable: {exports_dir}" if _is_writable_directory(exports_dir) else f"Exports directory is not writable: {exports_dir}",
        ),
        _check(
            "backups_dir",
            "Backups directory",
            "pass" if _is_writable_directory(backups_dir) else "fail",
            f"Backups directory is writable: {backups_dir}" if _is_writable_directory(backups_dir) else f"Backups directory is not writable: {backups_dir}",
        ),
        _build_mail_backend_check(mail_backend, is_production, auth_required_enabled, mail_outbox_dir, smtp_status),
        _build_smtp_configuration_check(mail_backend, smtp_status),
        _build_mail_from_check(mail_backend, mail_from_address),
        _check(
            "default_owner",
            "Default owner bootstrap",
            "warn" if default_owner_email == DEFAULT_OWNER_EMAIL else "pass",
            (
                "Default owner uses a custom email."
                if default_owner_email != DEFAULT_OWNER_EMAIL
                else "Default owner email is still the placeholder local value."
            ),
        ),
    ]

    counts = {
        "pass": sum(1 for item in checks if item["status"] == "pass"),
        "warn": sum(1 for item in checks if item["status"] == "warn"),
        "fail": sum(1 for item in checks if item["status"] == "fail"),
    }
    overall_status = "fail" if counts["fail"] else "warn" if counts["warn"] else "pass"

    return {
        "generated_at": _timestamp(),
        "environment": env_name,
        "overall_status": overall_status,
        "counts": counts,
        "ready_for_production": counts["fail"] == 0,
        "checks": checks,
        "recommended_actions": [item["message"] for item in checks if item["status"] != "pass"],
    }


def render_deploy_readiness_text(payload: dict) -> str:
    lines = [
        "Knowledge Hub Deploy Readiness",
        f"Generated at: {payload['generated_at']}",
        f"Environment: {payload['environment']}",
        f"Overall status: {payload['overall_status']}",
        "",
    ]

    for item in payload["checks"]:
        lines.append(f"[{item['status'].upper()}] {item['label']}: {item['message']}")

    if payload["recommended_actions"]:
        lines.append("")
        lines.append("Recommended actions:")
        for item in payload["recommended_actions"]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _build_database_check(database_url: str, data_dir: Path) -> dict:
    normalized = database_url.lower()
    if normalized.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
        db_path = Path(raw_path)
        in_data_dir = _is_relative_to(db_path, data_dir)
        return _check(
            "database",
            "Database location",
            "pass" if in_data_dir else "warn",
            (
                f"SQLite database is stored under the data directory: {db_path}"
                if in_data_dir
                else f"SQLite database is outside the main data directory: {db_path}"
            ),
        )

    if normalized.startswith("postgresql://") or normalized.startswith("postgres://"):
        return _check("database", "Database location", "pass", "External Postgres database is configured.")

    return _check("database", "Database location", "warn", "Database URL is set, but the engine is not recognized as SQLite or Postgres.")


def _build_mail_backend_check(
    mail_backend: str,
    is_production: bool,
    auth_required_enabled: bool,
    mail_outbox_dir: Path,
    smtp_status: dict,
) -> dict:
    if mail_backend == "disabled":
        return _check("mail_backend", "Mail backend", "fail", "Mail backend is disabled.")
    if mail_backend == "console":
        if is_production and auth_required_enabled:
            return _check(
                "mail_backend",
                "Mail backend",
                "fail",
                "Console mail backend cannot support production sign-in when KH_AUTH_REQUIRED=1.",
            )
        return _check(
            "mail_backend",
            "Mail backend",
            "warn" if is_production else "pass",
            "Console mail backend is only suitable for development."
            if is_production
            else "Console mail backend is acceptable for development.",
        )
    if mail_backend == "file":
        if is_production and auth_required_enabled:
            return _check(
                "mail_backend",
                "Mail backend",
                "fail",
                (
                    f"File outbox backend is still active at {mail_outbox_dir}. "
                    "Production sign-in with KH_AUTH_REQUIRED=1 needs real delivery."
                ),
            )
        return _check(
            "mail_backend",
            "Mail backend",
            "warn" if is_production else "pass",
            f"File outbox backend is active at {mail_outbox_dir}."
            if not is_production
            else f"File outbox backend is still active at {mail_outbox_dir}. Production will usually want real delivery.",
        )
    if mail_backend == "smtp":
        if smtp_status["config_errors"]:
            return _check(
                "mail_backend",
                "Mail backend",
                "fail",
                "SMTP backend is selected, but the configuration is still incomplete.",
            )
        return _check(
            "mail_backend",
            "Mail backend",
            "pass",
            (
                "SMTP backend is configured for real delivery."
                f" Target: {smtp_status['host']}:{smtp_status['port']}."
            ),
        )
    return _check("mail_backend", "Mail backend", "warn", f"Mail backend '{mail_backend}' is configured but not recognized by readiness checks.")


def _build_smtp_configuration_check(mail_backend: str, smtp_status: dict) -> dict:
    if mail_backend != "smtp":
        return _check("smtp_delivery", "SMTP delivery config", "pass", "SMTP config is not required for the current backend.")

    if smtp_status["config_errors"]:
        return _check(
            "smtp_delivery",
            "SMTP delivery config",
            "fail",
            "; ".join(smtp_status["config_errors"]),
        )

    if not smtp_status["authentication_configured"]:
        return _check(
            "smtp_delivery",
            "SMTP delivery config",
            "warn",
            (
                "SMTP is configured without username/password. "
                "That is fine for a trusted relay, but most external providers require auth."
            ),
        )

    return _check(
        "smtp_delivery",
        "SMTP delivery config",
        "pass",
        (
            f"SMTP auth is configured via {_smtp_transport_label(smtp_status)}"
            f" for {smtp_status['host']}:{smtp_status['port']}."
        ),
    )


def _build_mail_from_check(mail_backend: str, mail_from_address: str) -> dict:
    if mail_backend == "smtp" and not mail_from_address:
        return _check("mail_from", "Mail sender address", "fail", "SMTP delivery needs MAIL_FROM_ADDRESS.")
    if not mail_from_address:
        return _check("mail_from", "Mail sender address", "warn", "Mail sender address is empty.")
    if mail_from_address.endswith(".local"):
        return _check("mail_from", "Mail sender address", "warn", "Mail sender address still uses a local placeholder domain.")
    return _check("mail_from", "Mail sender address", "pass", "Mail sender address looks product-ready.")


def _build_public_base_url_check(public_base_url: str | None, is_production: bool) -> dict:
    if not public_base_url:
        return _check(
            "public_base_url",
            "Public base URL",
            "warn" if not is_production else "fail",
            (
                "Public base URL is not set yet."
                if not is_production
                else "Production should set KH_PUBLIC_BASE_URL so magic-link emails always use the right domain."
            ),
        )

    if is_local_base_url(public_base_url):
        return _check(
            "public_base_url",
            "Public base URL",
            "warn" if not is_production else "fail",
            f"Public base URL still points to a local or placeholder host: {public_base_url}",
        )

    if is_production and not public_base_url.startswith("https://"):
        return _check(
            "public_base_url",
            "Public base URL",
            "fail",
            "Production public base URL should use https.",
        )

    return _check(
        "public_base_url",
        "Public base URL",
        "pass",
        f"Public base URL looks usable: {public_base_url}",
    )


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".kh_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _check(check_id: str, label: str, status: str, message: str) -> dict:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
    }


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _smtp_transport_label(smtp_status: dict) -> str:
    if smtp_status.get("use_ssl"):
        return "SMTP over SSL"
    if smtp_status.get("use_tls"):
        return "SMTP with STARTTLS"
    return "plain SMTP"
