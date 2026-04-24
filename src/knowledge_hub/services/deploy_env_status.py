from __future__ import annotations

import os
from datetime import datetime, timezone

from .mail import get_smtp_status
from .public_urls import get_public_base_url
from ..utils import blank_to_none, is_local_base_url


PHASE_ONE = "phase_one"
PHASE_TWO = "phase_two"


def build_deploy_env_status(config) -> dict:
    env_name = str(config.get("ENV_NAME", "development")).strip().lower()
    is_production = env_name == "production"
    public_base_url = get_public_base_url(config)
    auth_required = bool(config.get("AUTH_REQUIRED", False))
    mail_backend = str(config.get("MAIL_BACKEND", "file")).strip().lower()
    smtp_status = get_smtp_status(config)
    secret_key = str(config.get("SECRET_KEY", ""))
    default_owner_email = str(config.get("DEFAULT_OWNER_EMAIL", "")).strip()
    default_owner_name = str(config.get("DEFAULT_OWNER_NAME", "")).strip()
    mail_from_address = str(config.get("MAIL_FROM_ADDRESS", "")).strip()
    mail_from_name = str(config.get("MAIL_FROM_NAME", "")).strip()

    items = [
        _item(
            key="KH_ENV",
            label="Environment",
            current_value=env_name,
            display_value=env_name,
            desired_value="production",
            phase=PHASE_ONE,
            status="pass" if is_production else "warn",
            message="Production mode is active." if is_production else "Still running in development mode.",
        ),
        _item(
            key="KH_DEBUG",
            label="Debug flag",
            current_value=_flag_value(config.get("DEBUG")),
            display_value=_flag_value(config.get("DEBUG")),
            desired_value="0",
            phase=PHASE_ONE,
            status="pass" if not bool(config.get("DEBUG")) else "warn",
            message="Debug mode is off." if not bool(config.get("DEBUG")) else "Debug mode is still enabled.",
        ),
        _item(
            key="KH_SECRET_KEY",
            label="Secret key",
            current_value=secret_key,
            display_value=_display_secret_key(secret_key),
            desired_value="<long random secret>",
            phase=PHASE_ONE,
            sensitive=True,
            status="pass" if _secret_is_ready(secret_key) else "fail",
            message="Secret key looks production-safe." if _secret_is_ready(secret_key) else "Secret key is still default or too short.",
        ),
        _item(
            key="KH_PUBLIC_BASE_URL",
            label="Public base URL",
            current_value=public_base_url or str(config.get("PUBLIC_BASE_URL", "")).strip(),
            display_value=public_base_url or _empty_marker(str(config.get("PUBLIC_BASE_URL", "")).strip()),
            desired_value="https://your-service.onrender.com",
            phase=PHASE_ONE,
            status=_public_base_url_status(public_base_url, is_production),
            message=_public_base_url_message(public_base_url, is_production),
        ),
        _item(
            key="KH_DEFAULT_OWNER_EMAIL",
            label="Default owner email",
            current_value=default_owner_email,
            display_value=_empty_marker(default_owner_email),
            desired_value="owner@yourdomain.com",
            phase=PHASE_ONE,
            status="pass" if _email_is_ready(default_owner_email) else "warn",
            message="Default owner email looks usable." if _email_is_ready(default_owner_email) else "Default owner email still looks like a placeholder.",
        ),
        _item(
            key="KH_DEFAULT_OWNER_NAME",
            label="Default owner name",
            current_value=default_owner_name,
            display_value=_empty_marker(default_owner_name),
            desired_value="Workspace Owner",
            phase=PHASE_ONE,
            status="pass" if not _is_placeholder_name(default_owner_name) else "warn",
            message="Default owner name looks customized." if not _is_placeholder_name(default_owner_name) else "Default owner name still looks generic.",
        ),
        _item(
            key="KH_MAIL_BACKEND",
            label="Mail backend",
            current_value=mail_backend,
            display_value=mail_backend,
            desired_value="smtp",
            phase=PHASE_ONE,
            status=_mail_backend_status(mail_backend, auth_required, is_production, smtp_status),
            message=_mail_backend_message(mail_backend, auth_required, is_production, smtp_status),
        ),
        _item(
            key="KH_MAIL_FROM_ADDRESS",
            label="Mail from address",
            current_value=mail_from_address,
            display_value=_empty_marker(mail_from_address),
            desired_value="noreply@yourdomain.com",
            phase=PHASE_ONE,
            status="pass" if _email_is_ready(mail_from_address) else "warn",
            message="Mail sender address looks product-ready." if _email_is_ready(mail_from_address) else "Mail sender address still looks like a placeholder.",
        ),
        _item(
            key="KH_MAIL_FROM_NAME",
            label="Mail from name",
            current_value=mail_from_name,
            display_value=_empty_marker(mail_from_name),
            desired_value="Knowledge Hub",
            phase=PHASE_ONE,
            status="pass" if not _is_placeholder_name(mail_from_name) else "warn",
            message="Mail sender name is set." if not _is_placeholder_name(mail_from_name) else "Mail sender name still uses a generic placeholder.",
        ),
        _item(
            key="KH_SMTP_HOST",
            label="SMTP host",
            current_value=smtp_status.get("host"),
            display_value=_empty_marker(smtp_status.get("host")),
            desired_value="smtp.provider.com",
            phase=PHASE_ONE,
            status="pass" if bool(smtp_status.get("host")) else "fail",
            message="SMTP host is configured." if smtp_status.get("host") else "SMTP host is still missing.",
        ),
        _item(
            key="KH_SMTP_PORT",
            label="SMTP port",
            current_value=str(smtp_status.get("port") or ""),
            display_value=str(smtp_status.get("port") or "-"),
            desired_value="587",
            phase=PHASE_ONE,
            status="pass" if _smtp_port_is_ready(smtp_status.get("port")) else "fail",
            message="SMTP port is configured." if _smtp_port_is_ready(smtp_status.get("port")) else "SMTP port is invalid.",
        ),
        _item(
            key="KH_SMTP_USERNAME",
            label="SMTP username",
            current_value=_env_value("KH_SMTP_USERNAME"),
            display_value=smtp_status.get("username_hint") or "(missing)",
            desired_value="<provider username>",
            phase=PHASE_ONE,
            status="pass" if smtp_status.get("authentication_configured") else "warn",
            message="SMTP authentication username is set." if smtp_status.get("authentication_configured") else "SMTP username is not configured yet.",
        ),
        _item(
            key="KH_SMTP_PASSWORD",
            label="SMTP password",
            current_value=_env_value("KH_SMTP_PASSWORD"),
            display_value="set" if smtp_status.get("has_password") else "(missing)",
            desired_value="<provider password>",
            phase=PHASE_ONE,
            sensitive=True,
            status="pass" if smtp_status.get("has_password") else "warn",
            message="SMTP password is set." if smtp_status.get("has_password") else "SMTP password is not configured yet.",
        ),
        _item(
            key="KH_SMTP_USE_TLS",
            label="SMTP STARTTLS",
            current_value=_flag_value(config.get("SMTP_USE_TLS")),
            display_value=_flag_value(config.get("SMTP_USE_TLS")),
            desired_value="1",
            phase=PHASE_ONE,
            status="pass" if not smtp_status.get("config_errors") else "warn",
            message=_smtp_transport_message(smtp_status),
        ),
        _item(
            key="KH_SMTP_USE_SSL",
            label="SMTP SSL",
            current_value=_flag_value(config.get("SMTP_USE_SSL")),
            display_value=_flag_value(config.get("SMTP_USE_SSL")),
            desired_value="0 or 1",
            phase=PHASE_ONE,
            status="pass" if not smtp_status.get("config_errors") else "warn",
            message=_smtp_transport_message(smtp_status),
        ),
        _item(
            key="KH_AUTH_REQUIRED",
            label="Private mode",
            current_value=_flag_value(auth_required),
            display_value=_flag_value(auth_required),
            desired_value="1 after email is verified",
            phase=PHASE_TWO,
            status=_auth_required_status(auth_required, mail_backend, smtp_status),
            message=_auth_required_message(auth_required, mail_backend, smtp_status),
        ),
    ]

    counts = {
        "pass": sum(1 for item in items if item["status"] == "pass"),
        "warn": sum(1 for item in items if item["status"] == "warn"),
        "fail": sum(1 for item in items if item["status"] == "fail"),
    }
    grouped = {
        PHASE_ONE: [item for item in items if item["phase"] == PHASE_ONE],
        PHASE_TWO: [item for item in items if item["phase"] == PHASE_TWO],
    }

    return {
        "generated_at": _timestamp(),
        "environment": env_name,
        "counts": counts,
        "items": items,
        "phase_one": grouped[PHASE_ONE],
        "phase_two": grouped[PHASE_TWO],
        "blocking_items": [item for item in items if item["status"] == "fail"],
        "warning_items": [item for item in items if item["status"] == "warn"],
        "ready_for_phase_one": all(item["status"] != "fail" for item in grouped[PHASE_ONE]),
        "ready_for_phase_two": all(item["status"] == "pass" for item in grouped[PHASE_TWO]),
        "next_actions": _unique_messages(item["message"] for item in items if item["status"] != "pass"),
    }


def render_deploy_env_status_text(payload: dict) -> str:
    lines = [
        "Knowledge Hub Deploy Env Status",
        f"Generated at: {payload['generated_at']}",
        f"Environment: {payload['environment']}",
        "",
        "Phase 1 variables:",
    ]
    for item in payload["phase_one"]:
        lines.append(_render_item_line(item))

    lines.append("")
    lines.append("Phase 2 variables:")
    for item in payload["phase_two"]:
        lines.append(_render_item_line(item))

    if payload["next_actions"]:
        lines.append("")
        lines.append("Next actions:")
        for item in payload["next_actions"]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _item(
    *,
    key: str,
    label: str,
    current_value,
    display_value: str,
    desired_value: str,
    phase: str,
    status: str,
    message: str,
    sensitive: bool = False,
) -> dict:
    return {
        "key": key,
        "label": label,
        "current_value": None if sensitive else current_value,
        "display_value": display_value,
        "desired_value": desired_value,
        "phase": phase,
        "status": status,
        "message": message,
        "source": "env" if _env_value(key) is not None else "default",
        "sensitive": sensitive,
    }


def _render_item_line(item: dict) -> str:
    return (
        f"[{item['status'].upper()}] {item['key']} ({item['source']}): "
        f"{item['display_value']} -> {item['message']}"
    )


def _env_value(key: str) -> str | None:
    return os.getenv(key)


def _flag_value(value) -> str:
    return "1" if bool(value) else "0"


def _display_secret_key(value: str) -> str:
    if not value:
        return "(missing)"
    if value == "knowledge-hub-dev-key":
        return "default dev key"
    return f"set ({len(value)} chars)"


def _secret_is_ready(value: str) -> bool:
    return bool(value and value != "knowledge-hub-dev-key" and len(value) >= 16)


def _email_is_ready(value: str | None) -> bool:
    cleaned = blank_to_none(value)
    return bool(cleaned and "@" in cleaned and not cleaned.endswith(".local"))


def _is_placeholder_name(value: str | None) -> bool:
    cleaned = blank_to_none(value)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    return lowered in {"workspace owner", "knowledge hub owner"}


def _empty_marker(value: str | None) -> str:
    cleaned = blank_to_none(value)
    return cleaned or "(missing)"


def _public_base_url_status(public_base_url: str | None, is_production: bool) -> str:
    if not public_base_url:
        return "fail" if is_production else "warn"
    if is_local_base_url(public_base_url):
        return "fail" if is_production else "warn"
    if is_production and not public_base_url.startswith("https://"):
        return "fail"
    return "pass"


def _public_base_url_message(public_base_url: str | None, is_production: bool) -> str:
    if not public_base_url:
        return (
            "Production still needs KH_PUBLIC_BASE_URL."
            if is_production
            else "Public base URL is not set yet."
        )
    if is_local_base_url(public_base_url):
        return f"Public base URL still points to a local or placeholder host: {public_base_url}"
    if is_production and not public_base_url.startswith("https://"):
        return "Production public base URL should use https."
    return f"Public base URL looks usable: {public_base_url}"


def _mail_backend_status(mail_backend: str, auth_required: bool, is_production: bool, smtp_status: dict) -> str:
    if mail_backend == "smtp":
        return "pass" if not smtp_status.get("config_errors") else "fail"
    if is_production and auth_required:
        return "fail"
    return "warn"


def _mail_backend_message(mail_backend: str, auth_required: bool, is_production: bool, smtp_status: dict) -> str:
    if mail_backend == "smtp":
        if smtp_status.get("config_errors"):
            return "SMTP backend is selected, but the config is still incomplete."
        return "SMTP backend is ready for real delivery."
    if is_production and auth_required:
        return "Private mode in production needs SMTP, not file or console delivery."
    if mail_backend == "file":
        return "File outbox is still active. Fine for local work, not ideal for live delivery."
    if mail_backend == "console":
        return "Console mail is only useful for debugging."
    if mail_backend == "disabled":
        return "Mail delivery is disabled."
    return f"Mail backend is set to {mail_backend}."


def _smtp_port_is_ready(port) -> bool:
    try:
        parsed = int(port)
    except (TypeError, ValueError):
        return False
    return 1 <= parsed <= 65535


def _smtp_transport_message(smtp_status: dict) -> str:
    if not smtp_status.get("host"):
        return "Transport flags are set, but SMTP host is still missing."
    if smtp_status.get("config_errors"):
        return "; ".join(smtp_status["config_errors"])
    if smtp_status.get("use_ssl"):
        return "SMTP will use direct SSL."
    if smtp_status.get("use_tls"):
        return "SMTP will use STARTTLS."
    return "SMTP is configured without TLS."


def _auth_required_status(auth_required: bool, mail_backend: str, smtp_status: dict) -> str:
    if auth_required and mail_backend != "smtp":
        return "fail"
    if auth_required and smtp_status.get("config_errors"):
        return "fail"
    if auth_required:
        return "pass"
    return "warn"


def _auth_required_message(auth_required: bool, mail_backend: str, smtp_status: dict) -> str:
    if auth_required and mail_backend != "smtp":
        return "Private mode is enabled, but real SMTP delivery is not ready."
    if auth_required and smtp_status.get("config_errors"):
        return "Private mode is enabled before SMTP config is complete."
    if auth_required:
        return "Private mode is enabled."
    return "Private mode is still off. Enable it after real email delivery is verified."


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_messages(messages) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for message in messages:
        cleaned = str(message or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items
