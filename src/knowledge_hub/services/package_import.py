from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .content_import import (
    UpsertResult,
    import_prompt_template_payload,
    import_snapshot_payload,
    upsert_project_record,
)
from .session_import import ImportResult, SessionImportError, import_session_payload


@dataclass
class ProjectPackageResult:
    workspace_slug: str | None
    project_slug: str
    project_created: bool
    session_logs: ImportResult
    prompt_templates: UpsertResult
    snapshots: UpsertResult


def import_project_package(
    db_session: Session,
    payload: Any,
    *,
    auto_create_project: bool = True,
    auto_create_workspace: bool = True,
    config=None,
    allowed_workspace_ids: set[int] | list[int] | None = None,
) -> ProjectPackageResult:
    if not isinstance(payload, dict):
        raise SessionImportError("Project package must be a JSON object.")

    project_payload = payload.get("project")
    logs_payload = payload.get("session_logs") or payload.get("logs") or []
    prompt_payload = payload.get("prompt_templates") or payload.get("prompts") or []
    snapshot_payload = payload.get("snapshots") or []

    try:
        if not isinstance(project_payload, dict):
            raise SessionImportError("Project package must include a 'project' object.")

        project, project_created = upsert_project_record(
            db_session,
            project_payload,
            auto_create_project=auto_create_project,
            auto_create_workspace=auto_create_workspace,
            config=config,
            allowed_workspace_ids=allowed_workspace_ids,
            commit=False,
        )

        log_result = import_session_payload(
            db_session,
            logs_payload,
            fallback_project_id=project.id,
            fallback_project_slug=project.slug,
            fallback_workspace_id=project.workspace_id,
            auto_create_project=auto_create_project,
            auto_create_workspace=auto_create_workspace,
            config=config,
            allowed_workspace_ids=allowed_workspace_ids,
            commit=False,
        ) if logs_payload else ImportResult(logs=[], skipped_logs=[], projects_created=[])

        prompt_result = import_prompt_template_payload(
            db_session,
            prompt_payload,
            fallback_project_id=project.id,
            fallback_project_slug=project.slug,
            fallback_workspace_id=project.workspace_id,
            auto_create_project=auto_create_project,
            auto_create_workspace=auto_create_workspace,
            config=config,
            allowed_workspace_ids=allowed_workspace_ids,
            commit=False,
        ) if prompt_payload else UpsertResult(created_items=[], updated_items=[], projects_created=[])

        snapshot_result = import_snapshot_payload(
            db_session,
            snapshot_payload,
            fallback_project_id=project.id,
            fallback_project_slug=project.slug,
            fallback_workspace_id=project.workspace_id,
            auto_create_project=auto_create_project,
            auto_create_workspace=auto_create_workspace,
            config=config,
            allowed_workspace_ids=allowed_workspace_ids,
            commit=False,
        ) if snapshot_payload else UpsertResult(created_items=[], updated_items=[], projects_created=[])

        db_session.commit()

        db_session.refresh(project)
        for item in log_result.logs:
            db_session.refresh(item)
        for item in prompt_result.created_items + prompt_result.updated_items:
            db_session.refresh(item)
        for item in snapshot_result.created_items + snapshot_result.updated_items:
            db_session.refresh(item)
    except Exception:
        db_session.rollback()
        raise

    return ProjectPackageResult(
        workspace_slug=project.workspace.slug if project.workspace is not None else None,
        project_slug=project.slug,
        project_created=project_created,
        session_logs=log_result,
        prompt_templates=prompt_result,
        snapshots=snapshot_result,
    )
