from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Workspace
from ..utils import blank_to_none, slugify, title_from_slug
from .ownership import ensure_workspace_owner


DEFAULT_WORKSPACE_SLUG = "personal"
DEFAULT_WORKSPACE_NAME = "Personal Workspace"


def ensure_default_workspace(db_session: Session, config=None, *, commit: bool = True) -> Workspace:
    slug = slugify(_config_value(config, "DEFAULT_WORKSPACE_SLUG", DEFAULT_WORKSPACE_SLUG)) or DEFAULT_WORKSPACE_SLUG
    name = blank_to_none(_config_value(config, "DEFAULT_WORKSPACE_NAME", DEFAULT_WORKSPACE_NAME)) or DEFAULT_WORKSPACE_NAME

    workspace = db_session.scalar(select(Workspace).where(Workspace.slug == slug))
    if workspace is None:
        workspace = Workspace(
            slug=slug,
            name=name,
            description="Default workspace for internal Knowledge Hub usage.",
            plan="internal",
            status="active",
        )
        db_session.add(workspace)
        if commit:
            db_session.commit()
            db_session.refresh(workspace)
        else:
            db_session.flush()
    ensure_workspace_owner(db_session, workspace, config=config, commit=commit)
    return workspace


def list_workspaces(db_session: Session) -> list[Workspace]:
    return db_session.scalars(select(Workspace).order_by(Workspace.name.asc(), Workspace.slug.asc())).all()


def resolve_workspace(
    db_session: Session,
    *,
    workspace_id: int | None = None,
    workspace_slug: str | None = None,
    workspace_name: str | None = None,
    auto_create: bool = True,
    config=None,
    commit: bool = False,
) -> tuple[Workspace, Workspace | None]:
    workspace = None
    workspace_created = None

    if workspace_id:
        workspace = db_session.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace with id {workspace_id} was not found.")

    normalized_slug = slugify(workspace_slug or "")
    if workspace is None and normalized_slug:
        workspace = db_session.scalar(select(Workspace).where(Workspace.slug == normalized_slug))

    if workspace is None and normalized_slug and auto_create:
        workspace = Workspace(
            slug=normalized_slug,
            name=blank_to_none(workspace_name) or title_from_slug(normalized_slug),
            description="Auto-created from import.",
            plan="internal",
            status="active",
        )
        db_session.add(workspace)
        if commit:
            db_session.commit()
            db_session.refresh(workspace)
        else:
            db_session.flush()
        workspace_created = workspace
        ensure_workspace_owner(db_session, workspace, config=config, commit=commit)

    if workspace is None:
        workspace = ensure_default_workspace(db_session, config, commit=commit)

    return workspace, workspace_created


def _config_value(config, key: str, fallback):
    if config is None:
        return fallback
    return config.get(key, fallback)
