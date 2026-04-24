from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import json
from pathlib import Path
import secrets
import smtplib
import ssl

from ..utils import blank_to_none, slugify


@dataclass
class MailDeliveryResult:
    backend: str
    to_email: str
    subject: str
    delivered_at: str
    preview_path: str | None = None
    message_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "to_email": self.to_email,
            "subject": self.subject,
            "delivered_at": self.delivered_at,
            "preview_path": self.preview_path,
            "message_id": self.message_id,
        }


def send_magic_login_email(
    config,
    *,
    to_email: str,
    user_display_name: str,
    login_url: str,
    ttl_minutes: int,
) -> MailDeliveryResult:
    subject = "Your Knowledge Hub sign-in link"
    greeting = user_display_name or to_email
    body_text = "\n".join(
        [
            f"Hello {greeting},",
            "",
            "Use this one-time link to sign in to Knowledge Hub:",
            login_url,
            "",
            f"This link expires in {ttl_minutes} minute(s).",
            "",
            "If you did not request this sign-in link, you can ignore this message.",
        ]
    )
    return send_email(
        config,
        to_email=to_email,
        subject=subject,
        text_body=body_text,
        metadata={"kind": "magic_login", "login_url": login_url, "ttl_minutes": ttl_minutes},
    )


def send_email(
    config,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    metadata: dict | None = None,
) -> MailDeliveryResult:
    backend = str(config.get("MAIL_BACKEND", "file")).strip().lower()
    normalized_email = (blank_to_none(to_email) or "").strip().lower()
    normalized_subject = blank_to_none(subject) or "Knowledge Hub message"
    if not normalized_email:
        raise ValueError("Email recipient is required.")
    if not text_body.strip():
        raise ValueError("Email body cannot be empty.")

    if backend == "file":
        return _write_outbox_message(
            config,
            to_email=normalized_email,
            subject=normalized_subject,
            text_body=text_body,
            metadata=metadata or {},
        )
    if backend == "console":
        payload = {
            "backend": backend,
            "to": normalized_email,
            "subject": normalized_subject,
            "body": text_body,
            "metadata": metadata or {},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return MailDeliveryResult(
            backend=backend,
            to_email=normalized_email,
            subject=normalized_subject,
            delivered_at=_timestamp(),
        )
    if backend == "smtp":
        return _send_smtp_message(
            config,
            to_email=normalized_email,
            subject=normalized_subject,
            text_body=text_body,
        )
    if backend == "disabled":
        raise ValueError("Email backend is disabled.")

    raise ValueError(f"Unsupported mail backend '{backend}'.")


def get_mail_status(config, *, limit: int = 5) -> dict:
    backend = str(config.get("MAIL_BACKEND", "file")).strip().lower()
    outbox_dir = Path(config["MAIL_OUTBOX_DIR"])
    smtp_status = get_smtp_status(config)
    smtp_payload = {
        **smtp_status,
        "active": backend == "smtp",
        "ready": smtp_status["ready"] if backend == "smtp" else None,
        "config_errors": smtp_status["config_errors"] if backend == "smtp" else [],
    }
    recent_messages = list_recent_outbox_messages(config, limit=limit) if backend == "file" else []
    return {
        "backend": backend,
        "from_address": config.get("MAIL_FROM_ADDRESS"),
        "from_name": config.get("MAIL_FROM_NAME"),
        "outbox_dir": str(outbox_dir),
        "recent_messages": recent_messages,
        "recent_messages_supported": backend == "file",
        "delivery_target": _build_delivery_target(backend, outbox_dir, smtp_payload),
        "transport": _build_transport_label(backend, smtp_payload),
        "delivery_hint": _build_delivery_hint(backend, outbox_dir, smtp_payload),
        "smtp": smtp_payload,
    }


def list_recent_outbox_messages(config, *, limit: int = 5) -> list[dict]:
    outbox_dir = Path(config["MAIL_OUTBOX_DIR"])
    if not outbox_dir.exists():
        return []

    files = sorted(outbox_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    items: list[dict] = []
    for path in files[: max(limit, 0)]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "message_id": payload.get("message_id"),
                "to_email": payload.get("to_email"),
                "subject": payload.get("subject"),
                "created_at": payload.get("created_at"),
                "path": str(path),
                "kind": (payload.get("metadata") or {}).get("kind"),
            }
        )
    return items


def get_smtp_status(config) -> dict:
    raw_host = blank_to_none(str(config.get("SMTP_HOST", "")))
    raw_username = blank_to_none(str(config.get("SMTP_USERNAME", "")))
    raw_password = blank_to_none(str(config.get("SMTP_PASSWORD", "")))
    try:
        port = int(config.get("SMTP_PORT", 587))
    except (TypeError, ValueError):
        port = 0

    use_tls = bool(config.get("SMTP_USE_TLS", True))
    use_ssl = bool(config.get("SMTP_USE_SSL", False))
    timeout_seconds = _read_timeout_seconds(config)
    errors: list[str] = []

    if not raw_host:
        errors.append("SMTP host is missing.")
    if port <= 0 or port > 65535:
        errors.append("SMTP port must be between 1 and 65535.")
    if use_tls and use_ssl:
        errors.append("Choose either STARTTLS or SSL for SMTP, not both.")
    if bool(raw_username) != bool(raw_password):
        errors.append("SMTP username and password must be set together.")

    return {
        "host": raw_host,
        "port": port,
        "username_hint": _mask_username(raw_username),
        "has_password": bool(raw_password),
        "authentication_configured": bool(raw_username and raw_password),
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "timeout_seconds": timeout_seconds,
        "config_errors": errors,
        "ready": len(errors) == 0,
    }


def _write_outbox_message(
    config,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    metadata: dict,
) -> MailDeliveryResult:
    outbox_dir = Path(config["MAIL_OUTBOX_DIR"])
    outbox_dir.mkdir(parents=True, exist_ok=True)
    message_id = secrets.token_hex(8)
    timestamp = datetime.now(timezone.utc)
    recipient_slug = slugify(to_email.split("@")[0]) or "recipient"
    filename = f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}_{recipient_slug}_{message_id}.json"
    path = outbox_dir / filename

    payload = {
        "message_id": message_id,
        "created_at": timestamp.isoformat(),
        "backend": "file",
        "from_address": config.get("MAIL_FROM_ADDRESS"),
        "from_name": config.get("MAIL_FROM_NAME"),
        "to_email": to_email,
        "subject": subject,
        "text_body": text_body,
        "metadata": metadata,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return MailDeliveryResult(
        backend="file",
        to_email=to_email,
        subject=subject,
        delivered_at=payload["created_at"],
        preview_path=str(path),
        message_id=message_id,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send_smtp_message(
    config,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> MailDeliveryResult:
    smtp_status = get_smtp_status(config)
    if smtp_status["config_errors"]:
        raise ValueError("SMTP is not configured correctly: " + "; ".join(smtp_status["config_errors"]))

    from_address = blank_to_none(str(config.get("MAIL_FROM_ADDRESS", "")))
    from_name = blank_to_none(str(config.get("MAIL_FROM_NAME", ""))) or "Knowledge Hub"
    if not from_address:
        raise ValueError("MAIL_FROM_ADDRESS must be set before SMTP delivery can work.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_address}>"
    message["To"] = to_email
    message["Date"] = formatdate(localtime=False)
    message_id = make_msgid()
    message["Message-ID"] = message_id
    message.set_content(text_body)
    smtp_username = blank_to_none(str(config.get("SMTP_USERNAME", "")))
    smtp_password = blank_to_none(str(config.get("SMTP_PASSWORD", "")))

    try:
        if smtp_status["use_ssl"]:
            with smtplib.SMTP_SSL(
                smtp_status["host"],
                smtp_status["port"],
                timeout=smtp_status["timeout_seconds"],
                context=ssl.create_default_context(),
            ) as smtp:
                _finalize_smtp_delivery(smtp, smtp_status, message, smtp_username, smtp_password)
        else:
            with smtplib.SMTP(
                smtp_status["host"],
                smtp_status["port"],
                timeout=smtp_status["timeout_seconds"],
            ) as smtp:
                _finalize_smtp_delivery(smtp, smtp_status, message, smtp_username, smtp_password)
    except (OSError, smtplib.SMTPException) as exc:
        raise ValueError(f"SMTP delivery failed: {exc}") from exc

    return MailDeliveryResult(
        backend="smtp",
        to_email=to_email,
        subject=subject,
        delivered_at=_timestamp(),
        message_id=message_id.strip("<>"),
    )


def _finalize_smtp_delivery(
    smtp,
    smtp_status: dict,
    message: EmailMessage,
    smtp_username: str | None,
    smtp_password: str | None,
) -> None:
    smtp.ehlo()
    if smtp_status["use_tls"]:
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
    if smtp_status["authentication_configured"]:
        smtp.login(smtp_username, smtp_password)
    smtp.send_message(message)


def _build_delivery_target(backend: str, outbox_dir: Path, smtp_status: dict) -> str:
    if backend == "smtp":
        host = smtp_status.get("host") or "SMTP host not set"
        port = smtp_status.get("port") or "-"
        return f"{host}:{port}"
    if backend == "console":
        return "stdout"
    if backend == "disabled":
        return "delivery disabled"
    return str(outbox_dir)


def _build_transport_label(backend: str, smtp_status: dict) -> str:
    if backend == "smtp":
        if smtp_status.get("use_ssl"):
            return "SMTP over SSL"
        if smtp_status.get("use_tls"):
            return "SMTP with STARTTLS"
        return "Plain SMTP"
    if backend == "console":
        return "Console output"
    if backend == "disabled":
        return "Disabled"
    return "File outbox"


def _build_delivery_hint(backend: str, outbox_dir: Path, smtp_status: dict) -> str:
    if backend == "smtp":
        if smtp_status["config_errors"]:
            return "SMTP backend is selected, but the configuration is still incomplete."
        return (
            "Knowledge Hub will attempt real email delivery through "
            f"{smtp_status['host']}:{smtp_status['port']}."
        )
    if backend == "console":
        return "Knowledge Hub prints emails to stdout for local debugging."
    if backend == "disabled":
        return "Email delivery is disabled right now."
    return f"Knowledge Hub writes emails into the local outbox at {outbox_dir}."


def _read_timeout_seconds(config) -> int:
    try:
        timeout = int(config.get("SMTP_TIMEOUT_SECONDS", 20))
    except (TypeError, ValueError):
        timeout = 20
    return max(timeout, 1)


def _mask_username(value: str | None) -> str | None:
    cleaned = blank_to_none(value)
    if not cleaned:
        return None
    if "@" in cleaned:
        local_part, domain = cleaned.split("@", 1)
        return f"{_mask_segment(local_part)}@{domain}"
    return _mask_segment(cleaned)


def _mask_segment(value: str) -> str:
    if len(value) <= 2:
        return value[0] + "*" if len(value) == 2 else "*"
    return value[:2] + "*" * (len(value) - 2)
