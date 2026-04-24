from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..utils import decode_text_bytes
from .content_import import import_prompt_template_payload, import_snapshot_payload
from .package_import import import_project_package
from .project_exports import refresh_project_export_bundles
from .automation_events import safe_record_automation_event, safe_record_events_for_projects
from .session_import import SessionImportError, import_session_payload


@dataclass
class InboxPaths:
    root: Path
    pending: Path
    processed: Path
    failed: Path


@dataclass
class InboxFileResult:
    source_name: str
    status: str
    payload_kind: str | None
    message: str
    destination_path: str
    error_report_path: str | None = None


@dataclass
class InboxProcessSummary:
    scanned_count: int
    success_count: int
    failed_count: int
    files: list[InboxFileResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_count": self.scanned_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "files": [
                {
                    "source_name": item.source_name,
                    "status": item.status,
                    "payload_kind": item.payload_kind,
                    "message": item.message,
                    "destination_path": item.destination_path,
                    "error_report_path": item.error_report_path,
                }
                for item in self.files
            ],
        }


def get_inbox_paths(config) -> InboxPaths:
    return InboxPaths(
        root=Path(config["INBOX_DIR"]),
        pending=Path(config["INBOX_PENDING_DIR"]),
        processed=Path(config["INBOX_PROCESSED_DIR"]),
        failed=Path(config["INBOX_FAILED_DIR"]),
    )


def get_inbox_status(config) -> dict[str, Any]:
    paths = get_inbox_paths(config)
    pending_files = sorted(paths.pending.glob("*.json"))
    processed_files = sorted(paths.processed.glob("*.json"))
    failed_files = sorted(paths.failed.glob("*.json"))
    failure_reports = sorted(paths.failed.glob("*.error.txt"))

    return {
        "root_dir": str(paths.root),
        "pending_dir": str(paths.pending),
        "processed_dir": str(paths.processed),
        "failed_dir": str(paths.failed),
        "pending_count": len(pending_files),
        "processed_count": len(processed_files),
        "failed_count": len(failed_files),
        "pending_files": [path.name for path in pending_files[:10]],
        "recent_failed_reports": [path.name for path in failure_reports[-5:]],
    }


def process_inbox(db_session: Session, config, *, limit: int | None = None) -> InboxProcessSummary:
    paths = get_inbox_paths(config)
    files = sorted(paths.pending.glob("*.json"), key=lambda path: path.name.lower())
    if limit is not None:
        files = files[:limit]

    results: list[InboxFileResult] = []
    for path in files:
        results.append(_process_one_file(db_session, path, paths, config))

    return InboxProcessSummary(
        scanned_count=len(files),
        success_count=sum(1 for item in results if item.status == "processed"),
        failed_count=sum(1 for item in results if item.status == "failed"),
        files=results,
    )


def _process_one_file(db_session: Session, path: Path, paths: InboxPaths, config) -> InboxFileResult:
    try:
        payload = json.loads(decode_text_bytes(path.read_bytes()).lstrip("\ufeff"))
        payload_kind, normalized_payload = _detect_payload_kind(payload)
        message = _apply_payload(db_session, config, payload_kind, normalized_payload)
        destination = _move_file(path, paths.processed)
        return InboxFileResult(
            source_name=path.name,
            status="processed",
            payload_kind=payload_kind,
            message=message,
            destination_path=str(destination),
        )
    except Exception as exc:
        failed_destination = _move_file(path, paths.failed)
        error_report = _write_error_report(failed_destination, exc)
        safe_record_automation_event(
            db_session,
            event_type="inbox_process",
            source="inbox",
            status="failed",
            message=f"Inbox file failed: {path.name}",
            details={
                "source_name": path.name,
                "error": str(exc),
                "destination_path": str(failed_destination),
                "error_report_path": str(error_report),
            },
        )
        return InboxFileResult(
            source_name=path.name,
            status="failed",
            payload_kind=None,
            message=str(exc),
            destination_path=str(failed_destination),
            error_report_path=str(error_report),
        )


def _apply_payload(db_session: Session, config, payload_kind: str, payload: Any) -> str:
    if payload_kind == "project_package":
        result = import_project_package(db_session, payload, auto_create_project=True, config=config)
        refresh_project_export_bundles(db_session, config, [result.project_slug])
        safe_record_automation_event(
            db_session,
            event_type="project_package_import",
            source="inbox",
            message=(
                f"Project package import completed from inbox. Logs imported {result.session_logs.imported_count}, "
                f"duplicates skipped {result.session_logs.skipped_count}."
            ),
            project_slug=result.project_slug,
            details={
                "session_logs_imported": result.session_logs.imported_count,
                "session_logs_skipped_duplicates": result.session_logs.skipped_count,
            },
        )
        return (
            f"Imported project package for {result.project_slug}: "
            f"{result.session_logs.imported_count} logs, "
            f"{result.session_logs.skipped_count} duplicate logs skipped, "
            f"{result.prompt_templates.created_count + result.prompt_templates.updated_count} prompt templates, "
            f"{result.snapshots.created_count + result.snapshots.updated_count} snapshots. "
            f"Refreshed project exports."
        )

    if payload_kind == "session_logs":
        result = import_session_payload(db_session, payload, auto_create_project=True, config=config)
        refresh_project_export_bundles(
            db_session,
            config,
            [log.project.slug for log in result.logs + result.skipped_logs],
        )
        safe_record_events_for_projects(
            db_session,
            project_slugs=[log.project.slug for log in result.logs + result.skipped_logs],
            event_type="session_log_import",
            source="inbox",
            message=(
                f"Session log import completed from inbox. Imported {result.imported_count}, "
                f"skipped duplicates {result.skipped_count}."
            ),
            details={
                "imported_count": result.imported_count,
                "skipped_duplicates": result.skipped_count,
            },
            log_global_if_empty=True,
        )
        return (
            f"Imported {result.imported_count} session logs, "
            f"skipped {result.skipped_count} duplicates, and refreshed project exports."
        )

    if payload_kind == "prompt_templates":
        result = import_prompt_template_payload(db_session, payload, auto_create_project=True, config=config)
        total = result.created_count + result.updated_count
        refresh_project_export_bundles(db_session, config, [item.project.slug for item in result.created_items + result.updated_items])
        safe_record_events_for_projects(
            db_session,
            project_slugs=[item.project.slug for item in result.created_items + result.updated_items],
            event_type="prompt_template_import",
            source="inbox",
            message=(
                f"Prompt template import completed from inbox. Created {result.created_count}, "
                f"updated {result.updated_count}."
            ),
            details={
                "created_count": result.created_count,
                "updated_count": result.updated_count,
            },
            log_global_if_empty=True,
        )
        return f"Imported {total} prompt templates and refreshed project exports."

    if payload_kind == "snapshots":
        result = import_snapshot_payload(db_session, payload, auto_create_project=True, config=config)
        total = result.created_count + result.updated_count
        refresh_project_export_bundles(db_session, config, [item.project.slug for item in result.created_items + result.updated_items])
        safe_record_events_for_projects(
            db_session,
            project_slugs=[item.project.slug for item in result.created_items + result.updated_items],
            event_type="snapshot_import",
            source="inbox",
            message=(
                f"Snapshot import completed from inbox. Created {result.created_count}, "
                f"updated {result.updated_count}."
            ),
            details={
                "created_count": result.created_count,
                "updated_count": result.updated_count,
            },
            log_global_if_empty=True,
        )
        return f"Imported {total} snapshots and refreshed project exports."

    raise SessionImportError(f"Unsupported inbox payload kind: {payload_kind}")


def _detect_payload_kind(payload: Any) -> tuple[str, Any]:
    if isinstance(payload, dict):
        explicit_kind = str(payload.get("kind") or payload.get("entity") or "").strip().lower()
        if explicit_kind in {"project_package", "package"}:
            return "project_package", payload.get("payload") or payload
        if explicit_kind in {"session_logs", "session_log", "logs", "log"}:
            return "session_logs", payload.get("items") or payload.get("logs") or payload.get("payload") or payload
        if explicit_kind in {"prompt_templates", "prompt_template", "prompts", "prompt"}:
            return "prompt_templates", payload.get("items") or payload.get("prompt_templates") or payload.get("payload") or payload
        if explicit_kind in {"snapshots", "snapshot"}:
            return "snapshots", payload.get("items") or payload.get("snapshots") or payload.get("payload") or payload

        if "project" in payload and any(key in payload for key in ("session_logs", "logs", "prompt_templates", "prompts", "snapshots")):
            return "project_package", payload
        if any(key in payload for key in ("actions_taken", "files_touched", "blockers", "next_step", "tags", "source", "task", "summary")):
            return "session_logs", payload
        if all(key in payload for key in ("type", "title", "content")):
            return "prompt_templates", payload
        if all(key in payload for key in ("title", "content")):
            return "snapshots", payload

    if isinstance(payload, list):
        if not payload:
            raise SessionImportError("Inbox JSON array is empty.")
        first_item = payload[0]
        if not isinstance(first_item, dict):
            raise SessionImportError("Inbox JSON array must contain JSON objects.")
        if all(key in first_item for key in ("type", "title", "content")):
            return "prompt_templates", payload
        if all(key in first_item for key in ("title", "content")):
            return "snapshots", payload
        return "session_logs", payload

    raise SessionImportError("Could not detect inbox payload kind from the JSON file.")


def _move_file(source: Path, destination_dir: Path) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}__{source.name}"
    candidate = destination_dir / base_name
    counter = 1
    while candidate.exists():
        candidate = destination_dir / f"{timestamp}_{counter:02d}__{source.name}"
        counter += 1
    return source.replace(candidate)


def _write_error_report(destination: Path, exc: Exception) -> Path:
    report_path = destination.with_suffix(destination.suffix + ".error.txt")
    report_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    return report_path
