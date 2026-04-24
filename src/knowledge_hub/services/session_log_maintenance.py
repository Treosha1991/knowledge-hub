from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, SessionLog
from .project_exports import ProjectExportPaths, refresh_project_export_bundles


@dataclass
class SessionLogDedupeResult:
    groups: list[dict]
    removed_logs: int
    touched_project_slugs: list[str]
    refreshed_exports: list[ProjectExportPaths]

    @property
    def duplicate_groups(self) -> int:
        return len(self.groups)

    @property
    def duplicate_logs(self) -> int:
        return sum(len(item["remove_log_ids"]) for item in self.groups)


def load_projects_for_dedupe(
    db_session: Session,
    *,
    project_slug: str | None = None,
    use_all: bool = False,
) -> list[Project]:
    if use_all:
        return db_session.scalars(select(Project).order_by(Project.slug.asc())).all()

    if not project_slug:
        raise ValueError("project_slug is required when use_all is False.")

    project = db_session.scalar(select(Project).where(Project.slug == project_slug))
    if project is None:
        raise ValueError(f"Project '{project_slug}' was not found.")
    return [project]


def find_duplicate_session_log_groups(
    db_session: Session,
    projects: list[Project],
) -> list[dict]:
    groups: list[dict] = []

    for project in projects:
        logs = db_session.scalars(
            select(SessionLog)
            .where(SessionLog.project_id == project.id)
            .order_by(SessionLog.created_at.asc(), SessionLog.id.asc())
        ).all()

        grouped: dict[str, list[SessionLog]] = defaultdict(list)
        for log in logs:
            grouped[log.raw_json or f"log:{log.id}"].append(log)

        for entries in grouped.values():
            if len(entries) < 2:
                continue
            keep = entries[0]
            remove = entries[1:]
            groups.append(
                {
                    "project_slug": project.slug,
                    "project_name": project.name,
                    "keep_log_id": keep.id,
                    "keep_created_at": keep.created_at.isoformat() if keep.created_at else None,
                    "remove_log_ids": [item.id for item in remove],
                    "task": keep.task,
                    "summary": keep.summary,
                }
            )

    return groups


def run_session_log_dedupe(
    db_session: Session,
    config,
    projects: list[Project],
    *,
    apply: bool,
) -> SessionLogDedupeResult:
    groups = find_duplicate_session_log_groups(db_session, projects)
    removed_logs = 0
    touched_project_slugs: list[str] = []
    refreshed_exports: list[ProjectExportPaths] = []

    if apply and groups:
        for item in groups:
            touched_project_slugs.append(item["project_slug"])
            for log_id in item["remove_log_ids"]:
                log = db_session.get(SessionLog, log_id)
                if log is not None:
                    db_session.delete(log)
                    removed_logs += 1
        db_session.commit()
        refreshed_exports = refresh_project_export_bundles(db_session, config, touched_project_slugs)

    return SessionLogDedupeResult(
        groups=groups,
        removed_logs=removed_logs,
        touched_project_slugs=touched_project_slugs,
        refreshed_exports=refreshed_exports,
    )
