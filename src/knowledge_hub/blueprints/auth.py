from __future__ import annotations

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from ..db import get_session
from ..services import (
    build_external_url,
    consume_login_token,
    get_mail_status,
    issue_login_token,
    safe_record_automation_event,
    send_magic_login_email,
    sign_in_user,
    sign_out_user,
)
from ..utils import sanitize_relative_path


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    session = get_session()
    form_data = {
        "email": request.args.get("email", "").strip(),
        "next": sanitize_relative_path(request.args.get("next")) or "",
    }
    errors: list[str] = []
    delivery = None

    if request.method == "POST":
        form_data["email"] = request.form.get("email", "").strip()
        form_data["next"] = sanitize_relative_path(request.form.get("next")) or ""
        try:
            user, login_token = issue_login_token(
                session,
                email=form_data["email"],
                config=current_app.config,
                commit=False,
            )
            magic_link = build_external_url(
                "auth.magic_login",
                current_app.config,
                token=login_token.token,
                next=form_data["next"] or None,
            )
            delivery = send_magic_login_email(
                current_app.config,
                to_email=user.email,
                user_display_name=user.display_name,
                login_url=magic_link,
                ttl_minutes=int(current_app.config.get("LOGIN_TOKEN_TTL_MINUTES", 30)),
            )
            session.commit()
            safe_record_automation_event(
                session,
                event_type="auth_magic_link_issue",
                source="ui",
                message=f"Issued and delivered login link for {user.email}.",
                details={
                    "user_email": user.email,
                    "mail_delivery": delivery.to_dict(),
                },
            )
            flash(
                "Magic login link delivered."
                if delivery.backend != "file"
                else "Magic login link written to the local outbox.",
                "success",
            )
        except ValueError as exc:
            session.rollback()
            safe_record_automation_event(
                session,
                event_type="auth_magic_link_issue",
                source="ui",
                status="error",
                message=f"Could not deliver a login link for {form_data['email'] or 'unknown user'}.",
                details={
                    "user_email": form_data["email"] or None,
                    "error": str(exc),
                    "mail_backend": current_app.config.get("MAIL_BACKEND"),
                },
            )
            errors.append(str(exc))
            flash("Could not deliver a login link. Check the email and try again.", "error")

    return render_template(
        "auth/login.html",
        page_title="Sign In",
        form_data=form_data,
        errors=errors,
        delivery=delivery,
        mail_status=get_mail_status(current_app.config, limit=3),
    )


@bp.get("/magic/<token>")
def magic_login(token: str):
    session = get_session()
    try:
        user = consume_login_token(session, token=token, commit=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("auth.login"))

    sign_in_user(user)
    safe_record_automation_event(
        session,
        event_type="auth_login",
        source="ui",
        message=f"Signed in as {user.email}.",
        details={"user_email": user.email},
    )
    flash(f"Signed in as {user.display_name}.", "success")
    next_target = sanitize_relative_path(request.args.get("next"))
    return redirect(next_target or url_for("main.home"))


@bp.post("/logout")
def logout():
    session = get_session()
    user = getattr(g, "current_actor", None)
    sign_out_user()
    if user is not None:
        safe_record_automation_event(
            session,
            event_type="auth_logout",
            source="ui",
            message=f"Signed out {user.email}.",
            details={"user_email": user.email},
        )
    flash("Signed out.", "success")
    return redirect(url_for("main.home"))
