from __future__ import annotations

import json
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .blueprints import register_blueprints
from .config import get_config
from .db import create_all, get_session, init_db
from .services import (
    actor_override_enabled,
    auth_required,
    endpoint_allows_anonymous,
    ensure_application_schema,
    list_accessible_workspace_ids,
    list_accessible_workspaces,
    process_inbox,
    resolve_request_actor,
    should_clear_actor_override,
)
from .services.access import DEV_ACTOR_COOKIE, DEV_ACTOR_QUERY_PARAM
from .utils import sanitize_relative_path


def create_app(config_object=None) -> Flask:
    config_class = config_object or get_config()
    config_class.init_app()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config_class)

    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_db(app)
    ensure_application_schema(app)
    register_blueprints(app)
    _register_request_context(app)
    _register_cli(app)
    _register_error_handlers(app)

    @app.context_processor
    def inject_layout_context() -> dict[str, str]:
        return {
            "app_name": "Knowledge Hub",
            "current_actor": getattr(g, "current_actor", None),
            "current_actor_source": getattr(g, "current_actor_source", None),
            "actor_override_enabled": actor_override_enabled(app.config),
            "auth_required": auth_required(app.config),
            "accessible_workspaces": getattr(g, "accessible_workspaces", []),
        }

    return app


def _register_request_context(app: Flask) -> None:
    @app.before_request
    def load_actor_context() -> None:
        session = get_session()
        try:
            actor, source = resolve_request_actor(session, app.config, request)
        except PermissionError as exc:
            abort(403, description=str(exc))

        if actor is None and auth_required(app.config) and not endpoint_allows_anonymous(request.endpoint):
            return _authentication_required_response(app)

        g.current_actor = actor
        g.current_actor_source = source
        g.accessible_workspace_ids = set(list_accessible_workspace_ids(session, actor)) if actor is not None else set()
        g.accessible_workspaces = list_accessible_workspaces(session, actor) if actor is not None else []

    @app.after_request
    def persist_actor_override(response):
        if not actor_override_enabled(app.config):
            return response

        if should_clear_actor_override(request):
            response.delete_cookie(DEV_ACTOR_COOKIE)
            return response

        requested_email = (
            request.args.get(DEV_ACTOR_QUERY_PARAM)
            or request.form.get(DEV_ACTOR_QUERY_PARAM)
        )
        cleaned_email = str(requested_email or "").strip().lower()
        if cleaned_email:
            response.set_cookie(
                DEV_ACTOR_COOKIE,
                cleaned_email,
                httponly=False,
                samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
                secure=bool(app.config.get("SESSION_COOKIE_SECURE")),
            )

        return response


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        ensure_application_schema(app)
        print(f"Initialized Knowledge Hub database at {app.config['DATABASE_URL']}")

    @app.cli.command("upgrade-schema")
    def upgrade_schema_command() -> None:
        ensure_application_schema(app)
        print("Knowledge Hub schema is up to date.")

    @app.cli.command("process-inbox")
    def process_inbox_command() -> None:
        create_all(app)
        summary = process_inbox(get_session(), app.config)
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def handle_forbidden(error):
        return (
            render_template(
                "error.html",
                page_title="Forbidden",
                error_title="Access denied",
                error_message=getattr(error, "description", None) or "You do not have access to this part of Knowledge Hub.",
            ),
            403,
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        return (
            render_template(
                "error.html",
                page_title="Not Found",
                error_title="Page not found",
                error_message="The page you requested does not exist.",
            ),
            404,
        )

    @app.errorhandler(500)
    def handle_server_error(_error):
        return (
            render_template(
                "error.html",
                page_title="Server Error",
                error_title="Something went wrong",
                error_message="Knowledge Hub hit an unexpected error. Check the logs and try again.",
            ),
            500,
        )


def _authentication_required_response(app: Flask):
    next_target = sanitize_relative_path(request.full_path[:-1] if request.full_path.endswith("?") else request.full_path) or request.path
    login_url = url_for("auth.login", next=next_target)
    if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": False, "error": "Authentication required.", "login_url": login_url}), 401
    flash("Sign in is required to access this workspace.", "error")
    return redirect(login_url)
