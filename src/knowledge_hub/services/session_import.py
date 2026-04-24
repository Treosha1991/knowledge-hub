from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, SessionLog
from ..utils import blank_to_none, normalize_string_list, slugify, title_from_slug
from .workspaces import resolve_workspace


class SessionImportError(ValueError):
    pass


@dataclass
class ImportResult:
    logs: list[SessionLog]
    skipped_logs: list[SessionLog]
    projects_created: list[Project]

    @property
    def imported_count(self) -> int:
        return len(self.logs)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_logs)


def parse_json_text(raw_json: str) -> Any:
    try:
        return json.loads(raw_json.lstrip("\ufeff"))
    except json.JSONDecodeError as exc:
        raise SessionImportError(f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.") from exc


def build_manual_session_payload(form_data) -> dict[str, Any]:
    return {
        "workspace_id": blank_to_none(form_data.get("workspace_id")),
        "workspace_slug": blank_to_none(form_data.get("workspace_slug")),
        "workspace_name": blank_to_none(form_data.get("workspace_name")),
        "project_slug": blank_to_none(form_data.get("project_slug")),
        "project_name": blank_to_none(form_data.get("project_name")),
        "source": blank_to_none(form_data.get("source")) or "manual",
        "task": blank_to_none(form_data.get("task")),
        "summary": blank_to_none(form_data.get("summary")),
        "actions_taken": normalize_string_list(form_data.get("actions_taken")),
        "files_touched": normalize_string_list(form_data.get("files_touched")),
        "blockers": normalize_string_list(form_data.get("blockers")),
        "next_step": blank_to_none(form_data.get("next_step")),
        "tags": normalize_string_list(form_data.get("tags")),
    }


def import_session_payload(
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
) -> ImportResult:
    items = _coerce_payload_items(payload)
    imported_logs: list[SessionLog] = []
    skipped_logs: list[SessionLog] = []
    created_projects: list[Project] = []

    try:
        for item in items:
            normalized = _normalize_session_log_payload(item)
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
                created_projects.append(project_created)

            existing_log = _find_duplicate_log(
                db_session,
                project_id=project.id,
                raw_json=normalized["raw_json"],
            )
            if existing_log is not None:
                skipped_logs.append(existing_log)
                continue

            log = SessionLog(
                project_id=project.id,
                source=normalized["source"],
                task=normalized["task"],
                summary=normalized["summary"],
                actions_taken=normalized["actions_taken"],
                files_touched=normalized["files_touched"],
                blockers=normalized["blockers"],
                next_step=normalized["next_step"],
                tags=normalized["tags"],
                raw_json=normalized["raw_json"],
            )
            db_session.add(log)
            imported_logs.append(log)

        if commit:
            db_session.commit()
        else:
            db_session.flush()
    except Exception:
        db_session.rollback()
        raise

    if commit:
        for log in imported_logs:
            db_session.refresh(log)

    return ImportResult(logs=imported_logs, skipped_logs=skipped_logs, projects_created=created_projects)


def _coerce_payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("logs"), list):
        items = payload["logs"]
    elif isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise SessionImportError("Session log payload must be a JSON object, a list of objects, or an object with a 'logs' list.")

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise SessionImportError("Each imported session log must be a JSON object.")
        normalized_items.append(item)
    return normalized_items


def _normalize_session_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    project_slug = None
    project_name = None
    project_value = payload.get("project")

    if isinstance(project_value, dict):
        project_slug = blank_to_none(project_value.get("slug"))
        project_name = blank_to_none(project_value.get("name"))
    elif isinstance(project_value, str):
        project_slug = blank_to_none(project_value)

    project_slug = slugify(
        project_slug
        or payload.get("project_slug")
        or payload.get("projectId")
        or ""
    ) or None
    project_name = project_name or blank_to_none(payload.get("project_name")) or blank_to_none(payload.get("project_title"))

    source = blank_to_none(str(payload.get("source", "manual"))) or "manual"

    return {
        "workspace_id": _coerce_int(payload.get("workspace_id")),
        "workspace_slug": slugify(payload.get("workspace_slug") or payload.get("workspace") or "") or None,
        "workspace_name": blank_to_none(payload.get("workspace_name")),
        "project_id": _coerce_int(payload.get("project_id")),
        "project_slug": project_slug,
        "project_name": project_name,
        "source": source.lower(),
        "task": blank_to_none(payload.get("task")),
        "summary": blank_to_none(payload.get("summary")),
        "actions_taken": normalize_string_list(payload.get("actions_taken") or payload.get("actions")),
        "files_touched": normalize_string_list(payload.get("files_touched") or payload.get("files")),
        "blockers": normalize_string_list(payload.get("blockers") or payload.get("blocking_issues")),
        "next_step": blank_to_none(payload.get("next_step")),
        "tags": normalize_string_list(payload.get("tags")),
        "raw_json": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    }


def resolve_project_for_import(
    db_session: Session,
    normalized_payload: dict[str, Any],
    *,
    fallback_project_id: int | None,
    fallback_project_slug: str | None,
    fallback_workspace_id: int | None,
    fallback_workspace_slug: str | None,
    auto_create_project: bool,
    auto_create_workspace: bool,
    config,
    allowed_workspace_ids: set[int] | list[int] | None = None,
) -> tuple[Project, Project | None]:
    project = None
    project_created = None

    project_id = normalized_payload["project_id"] or fallback_project_id
    project_slug = normalized_payload["project_slug"] or slugify(fallback_project_slug or "") or None
    project_name = normalized_payload["project_name"]

    if project_id:
        project = db_session.get(Project, project_id)
        if project is None:
            raise SessionImportError(f"Project with id {project_id} was not found.")
        _validate_workspace_access(project.workspace_id, allowed_workspace_ids)

    if project is None and project_slug:
        project = db_session.scalar(select(Project).where(Project.slug == project_slug))
        if project is not None:
            _validate_workspace_access(project.workspace_id, allowed_workspace_ids)

    if project is None and project_slug and auto_create_project:
        workspace, _workspace_created = resolve_workspace(
            db_session,
            workspace_id=normalized_payload["workspace_id"] or fallback_workspace_id,
            workspace_slug=normalized_payload["workspace_slug"] or fallback_workspace_slug,
            workspace_name=normalized_payload["workspace_name"],
            auto_create=auto_create_workspace,
            config=config,
            commit=False,
        )
        _validate_workspace_access(workspace.id, allowed_workspace_ids)
        project = Project(
            workspace_id=workspace.id,
            slug=project_slug,
            name=project_name or title_from_slug(project_slug),
            status="active",
            description="Auto-created from session log import.",
        )
        db_session.add(project)
        db_session.flush()
        project_created = project

    if project is None:
        raise SessionImportError(
            "Could not resolve a project. Provide project_slug, choose an existing project, or allow auto-create."
        )

    return project, project_created


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_duplicate_log(
    db_session: Session,
    *,
    project_id: int,
    raw_json: str,
) -> SessionLog | None:
    return db_session.scalar(
        select(SessionLog)
        .where(
            SessionLog.project_id == project_id,
            SessionLog.raw_json == raw_json,
        )
        .limit(1)
    )


def _validate_workspace_access(
    workspace_id: int | None,
    allowed_workspace_ids: set[int] | list[int] | None,
) -> None:
    if allowed_workspace_ids is None or workspace_id is None:
        return

    normalized_ids = {int(value) for value in allowed_workspace_ids if value is not None}
    if workspace_id not in normalized_ids:
        raise SessionImportError("You do not have access to that workspace or project.")
