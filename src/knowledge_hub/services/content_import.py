from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, PromptTemplate, Snapshot
from ..utils import blank_to_none, slugify, title_from_slug
from .session_import import SessionImportError, resolve_project_for_import
from .workspaces import resolve_workspace


@dataclass
class UpsertResult:
    created_items: list[Any]
    updated_items: list[Any]
    projects_created: list[Project]

    @property
    def created_count(self) -> int:
        return len(self.created_items)

    @property
    def updated_count(self) -> int:
        return len(self.updated_items)


def build_manual_prompt_payload(form_data) -> dict[str, Any]:
    return {
        "workspace_id": blank_to_none(form_data.get("workspace_id")),
        "workspace_slug": blank_to_none(form_data.get("workspace_slug")),
        "workspace_name": blank_to_none(form_data.get("workspace_name")),
        "project_slug": blank_to_none(form_data.get("project_slug")),
        "project_name": blank_to_none(form_data.get("project_name")),
        "type": blank_to_none(form_data.get("type")) or "other",
        "title": blank_to_none(form_data.get("title")),
        "content": blank_to_none(form_data.get("content")),
    }


def build_manual_snapshot_payload(form_data) -> dict[str, Any]:
    return {
        "workspace_id": blank_to_none(form_data.get("workspace_id")),
        "workspace_slug": blank_to_none(form_data.get("workspace_slug")),
        "workspace_name": blank_to_none(form_data.get("workspace_name")),
        "project_slug": blank_to_none(form_data.get("project_slug")),
        "project_name": blank_to_none(form_data.get("project_name")),
        "title": blank_to_none(form_data.get("title")),
        "content": blank_to_none(form_data.get("content")),
    }


def upsert_project_record(
    db_session: Session,
    payload: dict[str, Any],
    *,
    auto_create_project: bool = True,
    auto_create_workspace: bool = True,
    config=None,
    allowed_workspace_ids: set[int] | list[int] | None = None,
    commit: bool = True,
) -> tuple[Project, bool]:
    slug = slugify(payload.get("slug") or payload.get("project_slug") or "")
    name = blank_to_none(payload.get("name")) or title_from_slug(slug)

    if not slug:
        raise SessionImportError("Project payload must include slug.")

    project = db_session.scalar(select(Project).where(Project.slug == slug))
    created = False

    if project is not None:
        _validate_workspace_access(project.workspace_id, allowed_workspace_ids)

    if project is None:
        if not auto_create_project:
            raise SessionImportError(f"Project '{slug}' was not found and auto-create is disabled.")
        workspace, _workspace_created = resolve_workspace(
            db_session,
            workspace_id=_coerce_int(payload.get("workspace_id")),
            workspace_slug=payload.get("workspace_slug"),
            workspace_name=payload.get("workspace_name"),
            auto_create=auto_create_workspace,
            config=config,
            commit=False,
        )
        _validate_workspace_access(workspace.id, allowed_workspace_ids)
        project = Project(slug=slug, name=name, status="active", workspace_id=workspace.id)
        db_session.add(project)
        created = True

    project.name = name or project.name
    project.description = _pick_value(payload.get("description"), project.description)
    project.stack = _pick_value(payload.get("stack"), project.stack)
    project.status = _pick_value(payload.get("status"), project.status or "active")
    project.current_goal = _pick_value(payload.get("current_goal"), project.current_goal)
    project.rules = _pick_value(payload.get("rules"), project.rules)

    if commit:
        db_session.commit()
        db_session.refresh(project)
    else:
        db_session.flush()

    return project, created


def import_prompt_template_payload(
    db_session: Session,
    payload: Any,
    *,
    fallback_project_id: int | None = None,
    fallback_project_slug: str | None = None,
    fallback_workspace_id: int | None = None,
    fallback_workspace_slug: str | None = None,
    auto_create_project: bool = True,
    auto_create_workspace: bool = True,
    config=None,
    allowed_workspace_ids: set[int] | list[int] | None = None,
    commit: bool = True,
) -> UpsertResult:
    items = _coerce_items(payload, "prompt templates")
    created_items: list[PromptTemplate] = []
    updated_items: list[PromptTemplate] = []
    projects_created: list[Project] = []

    try:
        for item in items:
            normalized = _normalize_prompt_payload(item)
            project, project_created = resolve_project_for_import(
                db_session,
                normalized,
                fallback_project_id=fallback_project_id,
                fallback_project_slug=fallback_project_slug,
                fallback_workspace_id=fallback_workspace_id,
                fallback_workspace_slug=fallback_workspace_slug,
                auto_create_project=auto_create_project,
                auto_create_workspace=auto_create_workspace,
                config=config,
                allowed_workspace_ids=allowed_workspace_ids,
            )
            if project_created is not None:
                projects_created.append(project_created)

            prompt = db_session.scalar(
                select(PromptTemplate).where(
                    PromptTemplate.project_id == project.id,
                    PromptTemplate.title == normalized["title"],
                )
            )
            if prompt is None:
                prompt = PromptTemplate(
                    project_id=project.id,
                    type=normalized["type"],
                    title=normalized["title"],
                    content=normalized["content"],
                )
                db_session.add(prompt)
                created_items.append(prompt)
            else:
                prompt.type = normalized["type"]
                prompt.content = normalized["content"]
                updated_items.append(prompt)

        if commit:
            db_session.commit()
        else:
            db_session.flush()
    except Exception:
        db_session.rollback()
        raise

    if commit:
        for item in created_items + updated_items:
            db_session.refresh(item)

    return UpsertResult(
        created_items=created_items,
        updated_items=updated_items,
        projects_created=projects_created,
    )


def import_snapshot_payload(
    db_session: Session,
    payload: Any,
    *,
    fallback_project_id: int | None = None,
    fallback_project_slug: str | None = None,
    fallback_workspace_id: int | None = None,
    fallback_workspace_slug: str | None = None,
    auto_create_project: bool = True,
    auto_create_workspace: bool = True,
    config=None,
    allowed_workspace_ids: set[int] | list[int] | None = None,
    commit: bool = True,
) -> UpsertResult:
    items = _coerce_items(payload, "snapshots")
    created_items: list[Snapshot] = []
    updated_items: list[Snapshot] = []
    projects_created: list[Project] = []

    try:
        for item in items:
            normalized = _normalize_snapshot_payload(item)
            project, project_created = resolve_project_for_import(
                db_session,
                normalized,
                fallback_project_id=fallback_project_id,
                fallback_project_slug=fallback_project_slug,
                fallback_workspace_id=fallback_workspace_id,
                fallback_workspace_slug=fallback_workspace_slug,
                auto_create_project=auto_create_project,
                auto_create_workspace=auto_create_workspace,
                config=config,
                allowed_workspace_ids=allowed_workspace_ids,
            )
            if project_created is not None:
                projects_created.append(project_created)

            snapshot = db_session.scalar(
                select(Snapshot).where(
                    Snapshot.project_id == project.id,
                    Snapshot.title == normalized["title"],
                )
            )
            if snapshot is None:
                snapshot = Snapshot(
                    project_id=project.id,
                    title=normalized["title"],
                    content=normalized["content"],
                )
                db_session.add(snapshot)
                created_items.append(snapshot)
            else:
                snapshot.content = normalized["content"]
                updated_items.append(snapshot)

        if commit:
            db_session.commit()
        else:
            db_session.flush()
    except Exception:
        db_session.rollback()
        raise

    if commit:
        for item in created_items + updated_items:
            db_session.refresh(item)

    return UpsertResult(
        created_items=created_items,
        updated_items=updated_items,
        projects_created=projects_created,
    )


def _normalize_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = blank_to_none(payload.get("title"))
    content = blank_to_none(payload.get("content"))
    if not title or not content:
        raise SessionImportError("Prompt template import requires both title and content.")

    return {
        "workspace_id": _coerce_int(payload.get("workspace_id")),
        "workspace_slug": slugify(payload.get("workspace_slug") or payload.get("workspace") or "") or None,
        "workspace_name": blank_to_none(payload.get("workspace_name")),
        "project_id": _coerce_int(payload.get("project_id")),
        "project_slug": slugify(payload.get("project_slug") or payload.get("project") or "") or None,
        "project_name": blank_to_none(payload.get("project_name")),
        "type": blank_to_none(payload.get("type")) or "other",
        "title": title,
        "content": content,
    }


def _normalize_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = blank_to_none(payload.get("title"))
    content = blank_to_none(payload.get("content"))
    if not title or not content:
        raise SessionImportError("Snapshot import requires both title and content.")

    return {
        "workspace_id": _coerce_int(payload.get("workspace_id")),
        "workspace_slug": slugify(payload.get("workspace_slug") or payload.get("workspace") or "") or None,
        "workspace_name": blank_to_none(payload.get("workspace_name")),
        "project_id": _coerce_int(payload.get("project_id")),
        "project_slug": slugify(payload.get("project_slug") or payload.get("project") or "") or None,
        "project_name": blank_to_none(payload.get("project_name")),
        "title": title,
        "content": content,
    }


def _coerce_items(payload: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise SessionImportError(f"{label.capitalize()} payload must be a JSON object or a list of objects.")

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise SessionImportError(f"Each imported {label[:-1]} must be a JSON object.")
        normalized_items.append(item)
    return normalized_items


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_value(new_value, current_value):
    cleaned = blank_to_none(new_value)
    if cleaned is None:
        return current_value
    return cleaned


def _validate_workspace_access(
    workspace_id: int | None,
    allowed_workspace_ids: set[int] | list[int] | None,
) -> None:
    if allowed_workspace_ids is None or workspace_id is None:
        return

    normalized_ids = {int(value) for value in allowed_workspace_ids if value is not None}
    if workspace_id not in normalized_ids:
        raise SessionImportError("You do not have access to that workspace or project.")
