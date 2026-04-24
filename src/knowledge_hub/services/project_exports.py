from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project
from .assistant_ready import build_assistant_ready_pack, render_assistant_ready_text
from .chat_bootstrap import build_chat_bootstrap_pack, render_chat_bootstrap_text
from .context_pack import build_context_pack, render_context_pack_text


@dataclass
class ProjectExportPaths:
    project_slug: str
    root: Path
    chat_bootstrap_json: Path
    chat_bootstrap_text: Path
    assistant_ready_json: Path
    assistant_ready_text: Path
    context_pack_json: Path
    context_pack_text: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "project_slug": self.project_slug,
            "root": str(self.root),
            "chat_bootstrap_json": str(self.chat_bootstrap_json),
            "chat_bootstrap_text": str(self.chat_bootstrap_text),
            "assistant_ready_json": str(self.assistant_ready_json),
            "assistant_ready_text": str(self.assistant_ready_text),
            "context_pack_json": str(self.context_pack_json),
            "context_pack_text": str(self.context_pack_text),
        }


def get_project_export_paths(config, project_slug: str, *, create: bool = False) -> ProjectExportPaths:
    root = Path(config["PROJECT_EXPORTS_DIR"]) / project_slug
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return ProjectExportPaths(
        project_slug=project_slug,
        root=root,
        chat_bootstrap_json=root / "chat_bootstrap.json",
        chat_bootstrap_text=root / "chat_bootstrap.txt",
        assistant_ready_json=root / "assistant_ready.json",
        assistant_ready_text=root / "assistant_ready.txt",
        context_pack_json=root / "context_pack.json",
        context_pack_text=root / "context_pack.txt",
    )


def refresh_project_export_bundle(
    db_session: Session,
    config,
    project: Project | str,
) -> ProjectExportPaths:
    resolved_project = _resolve_project(db_session, project)
    paths = get_project_export_paths(config, resolved_project.slug, create=True)

    chat_bootstrap_pack = build_chat_bootstrap_pack(db_session, resolved_project)
    assistant_pack = build_assistant_ready_pack(db_session, resolved_project)
    context_pack = build_context_pack(db_session, resolved_project)

    _write_json(paths.chat_bootstrap_json, chat_bootstrap_pack)
    _write_text(paths.chat_bootstrap_text, render_chat_bootstrap_text(chat_bootstrap_pack))
    _write_json(paths.assistant_ready_json, assistant_pack)
    _write_text(paths.assistant_ready_text, render_assistant_ready_text(assistant_pack))
    _write_json(paths.context_pack_json, context_pack)
    _write_text(paths.context_pack_text, render_context_pack_text(context_pack))

    return paths


def refresh_project_export_bundles(
    db_session: Session,
    config,
    project_slugs: Iterable[str],
) -> list[ProjectExportPaths]:
    refreshed: list[ProjectExportPaths] = []
    seen: set[str] = set()

    for project_slug in project_slugs:
        if not project_slug:
            continue
        cleaned_slug = str(project_slug).strip()
        if not cleaned_slug or cleaned_slug in seen:
            continue
        seen.add(cleaned_slug)
        refreshed.append(refresh_project_export_bundle(db_session, config, cleaned_slug))

    return refreshed


def _resolve_project(db_session: Session, project: Project | str) -> Project:
    if isinstance(project, Project):
        return project

    resolved = db_session.scalar(select(Project).where(Project.slug == str(project)))
    if resolved is None:
        raise ValueError(f"Project '{project}' was not found while refreshing exports.")
    return resolved


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")
