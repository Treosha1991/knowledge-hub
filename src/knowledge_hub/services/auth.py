from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from flask import session as flask_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LoginToken, User
from ..utils import blank_to_none


SESSION_USER_ID_KEY = "kh_user_id"


def issue_login_token(
    db_session: Session,
    *,
    email: str,
    config,
    commit: bool = True,
) -> tuple[User, LoginToken]:
    normalized_email = (blank_to_none(email) or "").strip().lower()
    if not normalized_email:
        raise ValueError("Email is required.")

    user = db_session.scalar(select(User).where(User.email == normalized_email))
    if user is None or user.status != "active":
        raise ValueError("Active user with that email was not found.")

    ttl_minutes = int(config.get("LOGIN_TOKEN_TTL_MINUTES", 30))
    login_token = LoginToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose="login",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=max(ttl_minutes, 1)),
    )
    db_session.add(login_token)

    if commit:
        db_session.commit()
        db_session.refresh(login_token)
    else:
        db_session.flush()

    return user, login_token


def consume_login_token(
    db_session: Session,
    *,
    token: str,
    commit: bool = True,
) -> User:
    login_token = _load_active_login_token(db_session, token=token)
    user = login_token.user
    login_token.consumed_at = datetime.now(timezone.utc)
    if commit:
        db_session.commit()
        db_session.refresh(user)
    else:
        db_session.flush()

    return user


def preview_login_token(
    db_session: Session,
    *,
    token: str,
) -> User:
    login_token = _load_active_login_token(db_session, token=token)
    return login_token.user


def resolve_session_actor(db_session: Session) -> User | None:
    raw_user_id = flask_session.get(SESSION_USER_ID_KEY)
    if raw_user_id is None:
        return None
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        flask_session.pop(SESSION_USER_ID_KEY, None)
        return None

    user = db_session.get(User, user_id)
    if user is None or user.status != "active":
        flask_session.pop(SESSION_USER_ID_KEY, None)
        return None
    return user


def sign_in_user(user: User) -> None:
    flask_session[SESSION_USER_ID_KEY] = user.id


def sign_out_user() -> None:
    flask_session.pop(SESSION_USER_ID_KEY, None)


def _ensure_utc(value):
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load_active_login_token(
    db_session: Session,
    *,
    token: str,
) -> LoginToken:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        raise ValueError("Login token is required.")

    login_token = db_session.scalar(
        select(LoginToken).where(LoginToken.token == normalized_token)
    )
    if login_token is None:
        raise ValueError("Login token was not found.")
    if login_token.consumed_at is not None:
        raise ValueError("Login token has already been used.")
    if _ensure_utc(login_token.expires_at) <= datetime.now(timezone.utc):
        raise ValueError("Login token has expired.")

    user = login_token.user
    if user.status != "active":
        raise ValueError("User is not active.")
    return login_token
