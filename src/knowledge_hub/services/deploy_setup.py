from __future__ import annotations

from datetime import datetime, timezone

from .mail import get_smtp_status
from .public_urls import get_public_base_url
from ..utils import blank_to_none


def build_deploy_setup_guide(config) -> dict:
    public_base_url = get_public_base_url(config) or "https://your-service.onrender.com"
    default_owner_email = _value_or_placeholder(config.get("DEFAULT_OWNER_EMAIL"), "owner@yourdomain.com")
    default_owner_name = _value_or_placeholder(config.get("DEFAULT_OWNER_NAME"), "Workspace Owner")
    mail_from_address = _value_or_placeholder(config.get("MAIL_FROM_ADDRESS"), "noreply@yourdomain.com")
    mail_from_name = _value_or_placeholder(config.get("MAIL_FROM_NAME"), "Knowledge Hub")
    smtp_status = get_smtp_status(config)

    phase_one_env = [
        _env("KH_ENV", "production", ready=True),
        _env("KH_DEBUG", "0", ready=True),
        _env("KH_DATA_DIR", "/var/data/knowledge_hub", ready=True),
        _env("KH_SECRET_KEY", "<generate a long random secret>", ready=_secret_is_ready(config)),
        _env("KH_PUBLIC_BASE_URL", public_base_url, ready=get_public_base_url(config) is not None),
        _env("KH_DEFAULT_OWNER_EMAIL", default_owner_email, ready=_email_is_ready(default_owner_email)),
        _env("KH_DEFAULT_OWNER_NAME", default_owner_name, ready=not _is_placeholder_name(default_owner_name)),
        _env("KH_MAIL_BACKEND", "smtp", ready=str(config.get("MAIL_BACKEND", "file")).strip().lower() == "smtp"),
        _env("KH_MAIL_FROM_ADDRESS", mail_from_address, ready=_email_is_ready(mail_from_address)),
        _env("KH_MAIL_FROM_NAME", mail_from_name, ready=not _is_placeholder_name(mail_from_name)),
        _env("KH_SMTP_HOST", smtp_status.get("host") or "smtp.provider.com", ready=bool(smtp_status.get("host"))),
        _env("KH_SMTP_PORT", str(smtp_status.get("port") or 587), ready=bool(smtp_status.get("host"))),
        _env("KH_SMTP_USERNAME", "<provider username>", ready=smtp_status.get("authentication_configured", False)),
        _env("KH_SMTP_PASSWORD", "<provider password>", ready=smtp_status.get("has_password", False), sensitive=True),
        _env("KH_SMTP_USE_TLS", "1" if smtp_status.get("use_tls", True) else "0", ready=bool(smtp_status.get("host"))),
        _env("KH_SMTP_USE_SSL", "1" if smtp_status.get("use_ssl") else "0", ready=bool(smtp_status.get("host"))),
    ]
    phase_two_env = [
        _env("KH_AUTH_REQUIRED", "1", ready=bool(config.get("AUTH_REQUIRED", False))),
    ]

    setup = {
        "generated_at": _timestamp(),
        "render_service_name": "knowledge-hub",
        "public_base_url": public_base_url,
        "public_base_url_ready": get_public_base_url(config) is not None,
        "mail_backend": str(config.get("MAIL_BACKEND", "file")).strip().lower(),
        "auth_required": bool(config.get("AUTH_REQUIRED", False)),
        "phase_one_env": phase_one_env,
        "phase_two_env": phase_two_env,
        "safe_rollout_steps": [
            "Set the production env vars on Render, including KH_PUBLIC_BASE_URL and SMTP credentials.",
            "Keep KH_AUTH_REQUIRED=0 until one test email succeeds through the real SMTP provider.",
            "Run python tools/send_test_email.py your-email@example.com against the production config.",
            "Request one real magic login link and confirm that the email opens the correct public domain.",
            "Only then enable KH_AUTH_REQUIRED=1 and redeploy.",
        ],
        "blocking_gaps": _build_blocking_gaps(config, public_base_url, smtp_status, default_owner_email, mail_from_address),
        "copy_blocks": {
            "phase_one": render_env_block(_filter_phase_one_ready(phase_one_env)),
            "phase_two": render_env_block(phase_two_env),
        },
    }

    return setup


def render_env_block(items: list[dict]) -> str:
    return "\n".join(f"{item['key']}={item['value']}" for item in items)


def render_deploy_setup_text(payload: dict) -> str:
    lines = [
        "Knowledge Hub Deploy Setup",
        f"Generated at: {payload['generated_at']}",
        "",
        "Phase 1: real SMTP delivery before private mode",
        payload["copy_blocks"]["phase_one"],
        "",
        "Phase 2: enable private mode after email is verified",
        payload["copy_blocks"]["phase_two"],
        "",
        "Safe rollout steps:",
    ]
    for item in payload["safe_rollout_steps"]:
        lines.append(f"- {item}")

    if payload["blocking_gaps"]:
        lines.append("")
        lines.append("Blocking gaps:")
        for item in payload["blocking_gaps"]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _env(key: str, value: str, *, ready: bool, sensitive: bool = False) -> dict:
    return {
        "key": key,
        "value": value,
        "ready": ready,
        "sensitive": sensitive,
    }


def _filter_phase_one_ready(items: list[dict]) -> list[dict]:
    return items


def _build_blocking_gaps(config, public_base_url: str, smtp_status: dict, default_owner_email: str, mail_from_address: str) -> list[str]:
    gaps: list[str] = []
    if not get_public_base_url(config):
        gaps.append("KH_PUBLIC_BASE_URL is still missing or invalid.")
    if not _secret_is_ready(config):
        gaps.append("KH_SECRET_KEY is still default or too short.")
    if str(config.get("MAIL_BACKEND", "file")).strip().lower() != "smtp":
        gaps.append("KH_MAIL_BACKEND is not set to smtp yet.")
    if smtp_status.get("config_errors"):
        gaps.append("SMTP config is incomplete: " + "; ".join(smtp_status["config_errors"]))
    if not _email_is_ready(mail_from_address):
        gaps.append("KH_MAIL_FROM_ADDRESS still looks like a placeholder.")
    if not _email_is_ready(default_owner_email):
        gaps.append("KH_DEFAULT_OWNER_EMAIL still looks like a placeholder.")
    return gaps


def _secret_is_ready(config) -> bool:
    secret_key = str(config.get("SECRET_KEY", ""))
    return bool(secret_key and secret_key != "knowledge-hub-dev-key" and len(secret_key) >= 16)


def _email_is_ready(value: str | None) -> bool:
    cleaned = blank_to_none(value)
    return bool(cleaned and "@" in cleaned and not cleaned.endswith(".local"))


def _is_placeholder_name(value: str | None) -> bool:
    cleaned = blank_to_none(value)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    return lowered in {"workspace owner", "knowledge hub", "knowledge hub owner"}


def _value_or_placeholder(value: str | None, fallback: str) -> str:
    return blank_to_none(value) or fallback


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
