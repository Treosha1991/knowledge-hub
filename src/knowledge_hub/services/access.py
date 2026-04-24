from __future__ import annotations

from flask import Request
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from ..models import Project, User, Workspace, WorkspaceMembership
from .auth import resolve_session_actor
from .ownership import ensure_default_owner, get_workspace_membership


DEV_ACTOR_EMAIL_HEADER = "X-KH-User-Email"
DEV_ACTOR_QUERY_PARAM = "as_user"
DEV_ACTOR_COOKIE = "kh_actor_email"
DEV_ACTOR_CLEAR_PARAM = "clear_actor"
PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.magic_login",
    "auth.logout",
    "api.healthz",
    "api.gpt_actions_openapi",
    "main.healthz",
    "static",
}


def resolve_request_actor(
    db_session: Session,
    config,
    request: Request,
) -> tuple[User | None, str]:
    actor = ensure_default_owner(db_session, config, commit=False)
    if actor_override_enabled(config):
        requested_email = extract_requested_actor_email(request)
        if requested_email:
            normalized_email = requested_email.strip().lower()
            if normalized_email == actor.email.lower():
                return actor, "request_override"

            requested_user = db_session.scalar(select(User).where(User.email == normalized_email))
            if requested_user is None or requested_user.status != "active":
                raise PermissionError(f"Actor override user '{normalized_email}' was not found or is not active.")

            return requested_user, "request_override"

    session_actor = resolve_session_actor(db_session)
    if session_actor is not None:
        return session_actor, "session"

    if auth_required(config):
        return None, "anonymous"

    return actor, "default_owner"


def actor_override_enabled(config) -> bool:
    env_name = str(config.get("ENV_NAME", "development")).strip().lower()
    if env_name == "production":
        return False
    return bool(config.get("DEV_ACTOR_OVERRIDE_ENABLED", True))


def auth_required(config) -> bool:
    return bool(config.get("AUTH_REQUIRED", False))


def endpoint_allows_anonymous(endpoint: str | None) -> bool:
    cleaned = str(endpoint or "").strip()
    return cleaned in PUBLIC_ENDPOINTS or cleaned.startswith("static")


def extract_requested_actor_email(request: Request) -> str | None:
    for value in (
        request.headers.get(DEV_ACTOR_EMAIL_HEADER),
        request.args.get(DEV_ACTOR_QUERY_PARAM),
        request.form.get(DEV_ACTOR_QUERY_PARAM),
        request.cookies.get(DEV_ACTOR_COOKIE),
    ):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return None


def should_clear_actor_override(request: Request) -> bool:
    value = request.args.get(DEV_ACTOR_CLEAR_PARAM) or request.form.get(DEV_ACTOR_CLEAR_PARAM)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def list_accessible_workspace_ids(db_session: Session, actor: User) -> list[int]:
    return db_session.scalars(
        select(WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == actor.id,
            WorkspaceMembership.status == "active",
        )
        .order_by(WorkspaceMembership.workspace_id.asc())
    ).all()


def list_accessible_workspaces(db_session: Session, actor: User) -> list[Workspace]:
    return db_session.scalars(
        select(Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            WorkspaceMembership.user_id == actor.id,
            WorkspaceMembership.status == "active",
        )
        .order_by(Workspace.name.asc(), Workspace.slug.asc())
    ).all()


def list_accessible_project_ids(db_session: Session, actor: User) -> list[int]:
    return db_session.scalars(
        select(Project.id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Project.workspace_id)
        .where(
            WorkspaceMembership.user_id == actor.id,
            WorkspaceMembership.status == "active",
        )
        .order_by(Project.id.asc())
    ).all()


def get_default_accessible_workspace(db_session: Session, actor: User, config) -> Workspace | None:
    default_slug = str(config.get("DEFAULT_WORKSPACE_SLUG", "personal")).strip().lower()
    workspace = get_workspace_for_actor(db_session, actor, default_slug)
    if workspace is not None:
        return workspace

    workspaces = list_accessible_workspaces(db_session, actor)
    return workspaces[0] if workspaces else None


def get_workspace_for_actor(db_session: Session, actor: User, slug: str) -> Workspace | None:
    cleaned_slug = str(slug or "").strip()
    if not cleaned_slug:
        return None
    return db_session.scalar(
        select(Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            Workspace.slug == cleaned_slug,
            WorkspaceMembership.user_id == actor.id,
            WorkspaceMembership.status == "active",
        )
    )


def get_project_for_actor(db_session: Session, actor: User, slug: str) -> Project | None:
    cleaned_slug = str(slug or "").strip()
    if not cleaned_slug:
        return None
    return db_session.scalar(
        select(Project)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Project.workspace_id)
        .where(
            Project.slug == cleaned_slug,
            WorkspaceMembership.user_id == actor.id,
            WorkspaceMembership.status == "active",
        )
    )


def require_workspace_role(
    db_session: Session,
    workspace: Workspace,
    actor: User,
    *,
    roles: set[str],
) -> WorkspaceMembership:
    membership = get_workspace_membership(db_session, workspace, actor)
    if membership is None or membership.status != "active" or membership.role not in roles:
        allowed = ", ".join(sorted(roles))
        raise PermissionError(f"You need workspace role {allowed} to do that.")
    return membership


def scope_project_statement(statement, workspace_ids: set[int] | list[int]):
    ids = sorted({int(value) for value in workspace_ids if value is not None})
    if not ids:
        return statement.where(false())
    return statement.where(Project.workspace_id.in_(ids))
