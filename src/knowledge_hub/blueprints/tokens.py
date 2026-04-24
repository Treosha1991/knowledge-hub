from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_session
from ..services import (
    issue_api_token,
    list_user_api_tokens,
    revoke_api_token,
    safe_record_automation_event,
    serialize_api_token,
)


bp = Blueprint("tokens", __name__, url_prefix="/settings/api-tokens")


@bp.route("/", methods=["GET", "POST"])
def index():
    session = get_session()
    form_data = {
        "label": request.form.get("label", "").strip() if request.method == "POST" else "",
        "expires_in_days": request.form.get("expires_in_days", "").strip() if request.method == "POST" else "90",
    }
    errors: list[str] = []
    issued_token = None

    if request.method == "POST":
        try:
            expires_in_days = _parse_expiry_days(form_data["expires_in_days"])
            issued_token = issue_api_token(
                session,
                user=g.current_actor,
                label=form_data["label"],
                expires_in_days=expires_in_days,
                commit=True,
            )
            safe_record_automation_event(
                session,
                event_type="api_token_create",
                source="ui",
                message=f"Created API token '{issued_token.record.label}' for {g.current_actor.email}.",
                details={
                    "user_email": g.current_actor.email,
                    "token_id": issued_token.record.id,
                    "token_prefix": issued_token.record.token_prefix,
                    "expires_at": issued_token.record.expires_at.isoformat() if issued_token.record.expires_at else None,
                },
            )
            flash("API token created. Copy it now, it will not be shown again.", "success")
            form_data = {"label": "", "expires_in_days": "90"}
        except ValueError as exc:
            session.rollback()
            errors.append(str(exc))
            flash("Could not create the API token. Fix the form and try again.", "error")

    tokens = [serialize_api_token(item) for item in list_user_api_tokens(session, g.current_actor)]
    return render_template(
        "tokens/index.html",
        page_title="API Tokens",
        tokens=tokens,
        errors=errors,
        form_data=form_data,
        issued_token=issued_token,
    )


@bp.post("/<int:token_id>/revoke")
def revoke(token_id: int):
    session = get_session()
    try:
        token_record = revoke_api_token(session, token_id=token_id, user=g.current_actor, commit=True)
        safe_record_automation_event(
            session,
            event_type="api_token_revoke",
            source="ui",
            message=f"Revoked API token '{token_record.label}' for {g.current_actor.email}.",
            details={
                "user_email": g.current_actor.email,
                "token_id": token_record.id,
                "token_prefix": token_record.token_prefix,
            },
        )
        flash(f"Revoked API token '{token_record.label}'.", "success")
    except ValueError as exc:
        session.rollback()
        flash(str(exc), "error")

    return redirect(url_for("tokens.index"))


def _parse_expiry_days(raw_value: str) -> int | None:
    cleaned = str(raw_value or "").strip()
    if not cleaned:
        return 90
    if cleaned.lower() in {"none", "never", "no-expiry"}:
        return None
    try:
        value = int(cleaned)
    except ValueError as exc:
        raise ValueError("Expiry days must be a number or left blank.") from exc
    if value <= 0:
        raise ValueError("Expiry days must be greater than zero.")
    return value
