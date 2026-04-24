from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from flask import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApiToken, User
from ..utils import blank_to_none


TOKEN_PREFIX = "khp_"
DEFAULT_TOKEN_SCOPES = ["context_read", "chat_ingest"]


@dataclass(frozen=True)
class IssuedApiToken:
    record: ApiToken
    plaintext_token: str


def issue_api_token(
    db_session: Session,
    *,
    user: User,
    label: str,
    scopes: list[str] | None = None,
    expires_in_days: int | None = None,
    commit: bool = True,
) -> IssuedApiToken:
    normalized_label = blank_to_none(label)
    if user.status != "active":
        raise ValueError("Only active users can issue API tokens.")
    if not normalized_label:
        raise ValueError("Token label is required.")

    raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=max(int(expires_in_days), 1))

    token_record = ApiToken(
        user_id=user.id,
        label=normalized_label,
        token_prefix=raw_token[:12],
        token_hash=_hash_api_token(raw_token),
        scopes=_normalize_scopes(scopes),
        status="active",
        expires_at=expires_at,
    )
    db_session.add(token_record)

    if commit:
        db_session.commit()
        db_session.refresh(token_record)
    else:
        db_session.flush()

    return IssuedApiToken(record=token_record, plaintext_token=raw_token)


def authenticate_api_token(
    db_session: Session,
    *,
    plaintext_token: str,
    required_scope: str | None = None,
    commit: bool = True,
) -> tuple[User, ApiToken]:
    cleaned_token = str(plaintext_token or "").strip()
    if not cleaned_token:
        raise ValueError("API token is required.")

    token_record = db_session.scalar(
        select(ApiToken).where(ApiToken.token_hash == _hash_api_token(cleaned_token))
    )
    if token_record is None:
        raise ValueError("API token is invalid.")
    if token_record.status != "active":
        raise ValueError("API token is not active.")
    if token_record.expires_at is not None and _ensure_utc(token_record.expires_at) <= datetime.now(timezone.utc):
        raise ValueError("API token has expired.")
    if required_scope and required_scope not in set(token_record.scopes or []):
        raise ValueError(f"API token is missing required scope '{required_scope}'.")

    user = token_record.user
    if user is None or user.status != "active":
        raise ValueError("API token user is not active.")

    token_record.last_used_at = datetime.now(timezone.utc)
    if commit:
        db_session.commit()
        db_session.refresh(token_record)
    else:
        db_session.flush()

    return user, token_record


def extract_api_token_from_request(request: Request) -> str | None:
    authorization = str(request.headers.get("Authorization", "")).strip()
    if authorization.lower().startswith("bearer "):
        value = authorization[7:].strip()
        if value:
            return value

    fallback = str(request.headers.get("X-KH-API-Token", "")).strip()
    return fallback or None


def list_user_api_tokens(db_session: Session, user: User) -> list[ApiToken]:
    return db_session.scalars(
        select(ApiToken)
        .where(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    ).all()


def revoke_api_token(
    db_session: Session,
    *,
    token_id: int,
    user: User,
    commit: bool = True,
) -> ApiToken:
    token_record = db_session.scalar(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == user.id,
        )
    )
    if token_record is None:
        raise ValueError("API token was not found.")
    if token_record.status == "revoked":
        raise ValueError("API token is already revoked.")

    token_record.status = "revoked"
    if commit:
        db_session.commit()
        db_session.refresh(token_record)
    else:
        db_session.flush()
    return token_record


def serialize_api_token(token_record: ApiToken) -> dict:
    return {
        "id": token_record.id,
        "label": token_record.label,
        "token_prefix": token_record.token_prefix,
        "scopes": list(token_record.scopes or []),
        "status": token_record.status,
        "created_at": token_record.created_at.isoformat() if token_record.created_at else None,
        "updated_at": token_record.updated_at.isoformat() if token_record.updated_at else None,
        "expires_at": token_record.expires_at.isoformat() if token_record.expires_at else None,
        "last_used_at": token_record.last_used_at.isoformat() if token_record.last_used_at else None,
    }


def _hash_api_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_scopes(scopes: list[str] | None) -> list[str]:
    raw_values = scopes or DEFAULT_TOKEN_SCOPES
    items: list[str] = []
    for item in raw_values:
        cleaned = blank_to_none(str(item))
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items or list(DEFAULT_TOKEN_SCOPES)


def _ensure_utc(value):
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
