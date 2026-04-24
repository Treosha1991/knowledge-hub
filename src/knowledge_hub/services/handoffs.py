from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project
from ..utils import decode_text_bytes, format_datetime
from .project_exports import refresh_project_export_bundle


def build_ready_for_next_chat(
    db_session: Session,
    config,
    project: Project | str,
) -> dict:
    resolved_project = _resolve_project(db_session, project)
    export_paths = _ensure_chat_bootstrap_exports(db_session, config, resolved_project)

    handoff_text = decode_text_bytes(export_paths.chat_bootstrap_text.read_bytes())
    handoff_payload = json.loads(decode_text_bytes(export_paths.chat_bootstrap_json.read_bytes()))

    return {
        "kind": "chat_bootstrap",
        "project": {
            "id": resolved_project.id,
            "slug": resolved_project.slug,
            "name": resolved_project.name,
            "status": resolved_project.status,
            "description": resolved_project.description,
            "current_goal": resolved_project.current_goal,
            "updated_at": format_datetime(resolved_project.updated_at),
        },
        "handoff_updated_at": _file_timestamp(export_paths.chat_bootstrap_text),
        "text": handoff_text,
        "export_paths": export_paths.to_dict(),
        "chat_bootstrap": handoff_payload,
    }


def list_latest_handoffs(
    db_session: Session,
    config,
    *,
    limit: int = 8,
    accessible_workspace_ids: set[int] | list[int] | None = None,
) -> list[dict]:
    statement = select(Project).order_by(Project.updated_at.desc())
    if accessible_workspace_ids is not None:
        workspace_ids = sorted({int(value) for value in accessible_workspace_ids if value is not None})
        if workspace_ids:
            statement = select(Project).where(Project.workspace_id.in_(workspace_ids)).order_by(Project.updated_at.desc())
        else:
            statement = select(Project).where(Project.id == -1)

    projects = db_session.scalars(statement).all()
    items: list[tuple[float, dict]] = []

    for project in projects:
        export_paths = _ensure_chat_bootstrap_exports(db_session, config, project)
        handoff_text = decode_text_bytes(export_paths.chat_bootstrap_text.read_bytes())
        timestamp = export_paths.chat_bootstrap_text.stat().st_mtime
        items.append(
            (
                timestamp,
                {
                    "project_slug": project.slug,
                    "project_name": project.name,
                    "project_status": project.status,
                    "current_goal": project.current_goal,
                    "handoff_updated_at": _file_timestamp(export_paths.chat_bootstrap_text),
                    "preview": _build_preview(handoff_text),
                    "export_paths": export_paths.to_dict(),
                },
            )
        )

    items.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in items[: max(limit, 0)]]


def _ensure_chat_bootstrap_exports(db_session: Session, config, project: Project):
    return refresh_project_export_bundle(db_session, config, project)


def _resolve_project(db_session: Session, project: Project | str) -> Project:
    if isinstance(project, Project):
        return project

    resolved = db_session.scalar(select(Project).where(Project.slug == str(project)))
    if resolved is None:
        raise ValueError(f"Project '{project}' was not found.")
    return resolved


def _file_timestamp(path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _build_preview(handoff_text: str, *, max_length: int = 220) -> str:
    compact = " ".join(line.strip() for line in handoff_text.splitlines() if line.strip())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + "..."
