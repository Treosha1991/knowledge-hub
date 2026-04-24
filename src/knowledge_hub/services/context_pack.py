from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, PromptTemplate, SessionLog, Snapshot
from ..utils import format_datetime


def build_context_pack(
    db_session: Session,
    project: Project,
    *,
    log_limit: int = 8,
    prompt_limit: int = 5,
    snapshot_limit: int = 3,
) -> dict:
    recent_logs = db_session.scalars(
        select(SessionLog)
        .where(SessionLog.project_id == project.id)
        .order_by(SessionLog.created_at.desc())
        .limit(log_limit)
    ).all()
    recent_prompts = db_session.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.project_id == project.id)
        .order_by(PromptTemplate.updated_at.desc())
        .limit(prompt_limit)
    ).all()
    recent_snapshots = db_session.scalars(
        select(Snapshot)
        .where(Snapshot.project_id == project.id)
        .order_by(Snapshot.updated_at.desc())
        .limit(snapshot_limit)
    ).all()

    blockers = _unique_strings(blocker for log in recent_logs for blocker in log.blockers)
    next_steps = _unique_strings(log.next_step for log in recent_logs if log.next_step)
    tags = _unique_strings(tag for log in recent_logs for tag in log.tags)
    files_touched = _unique_strings(item for log in recent_logs for item in log.files_touched)

    latest_snapshot = recent_snapshots[0] if recent_snapshots else None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": project.id,
            "slug": project.slug,
            "name": project.name,
            "description": project.description,
            "stack": project.stack,
            "status": project.status,
            "current_goal": project.current_goal,
            "rules": project.rules,
            "created_at": format_datetime(project.created_at),
            "updated_at": format_datetime(project.updated_at),
        },
        "latest_snapshot": _serialize_snapshot(latest_snapshot),
        "recent_snapshots": [_serialize_snapshot(snapshot) for snapshot in recent_snapshots],
        "recent_logs": [_serialize_log(log) for log in recent_logs],
        "prompt_templates": [_serialize_prompt(prompt) for prompt in recent_prompts],
        "derived": {
            "active_blockers": blockers,
            "recent_tags": tags,
            "files_touched": files_touched,
            "next_steps": next_steps,
            "recommended_next_step": next_steps[0] if next_steps else project.current_goal,
        },
    }


def render_context_pack_text(context_pack: dict) -> str:
    project = context_pack["project"]
    latest_snapshot = context_pack["latest_snapshot"]
    derived = context_pack["derived"]
    recent_logs = context_pack["recent_logs"]
    prompt_templates = context_pack["prompt_templates"]

    lines = [
        "Knowledge Hub Context Pack",
        f"Generated at: {context_pack['generated_at']}",
        "",
        "Project",
        f"- Name: {project['name']}",
        f"- Slug: {project['slug']}",
        f"- Status: {project['status']}",
        f"- Stack: {project['stack'] or 'Not set'}",
        f"- Current goal: {project['current_goal'] or 'Not set'}",
        f"- Description: {project['description'] or 'Not set'}",
        "",
        "Project Rules",
        project["rules"] or "No rules captured yet.",
        "",
        "Recommended Next Step",
        derived["recommended_next_step"] or "Not captured yet.",
        "",
        "Active Blockers",
    ]

    if derived["active_blockers"]:
        lines.extend(f"- {item}" for item in derived["active_blockers"])
    else:
        lines.append("- None recorded.")

    lines.extend(["", "Recent Tags"])
    if derived["recent_tags"]:
        lines.extend(f"- {item}" for item in derived["recent_tags"])
    else:
        lines.append("- None recorded.")

    lines.extend(["", "Files Touched Recently"])
    if derived["files_touched"]:
        lines.extend(f"- {item}" for item in derived["files_touched"])
    else:
        lines.append("- None recorded.")

    lines.extend(["", "Latest Snapshot"])
    if latest_snapshot is not None:
        lines.append(f"- Title: {latest_snapshot['title']}")
        lines.append(latest_snapshot["content"] or "No content.")
    else:
        lines.append("No snapshot stored yet.")

    lines.extend(["", "Recent Session Logs"])
    if recent_logs:
        for log in recent_logs:
            lines.append(f"- {log['created_at'] or 'Unknown time'} | {log['source']} | {log['task'] or 'Untitled session'}")
            if log["summary"]:
                lines.append(f"  Summary: {log['summary']}")
            if log["actions_taken"]:
                lines.append(f"  Actions: {', '.join(log['actions_taken'])}")
            if log["next_step"]:
                lines.append(f"  Next step: {log['next_step']}")
    else:
        lines.append("No session logs stored yet.")

    lines.extend(["", "Reusable Prompt Templates"])
    if prompt_templates:
        for prompt in prompt_templates:
            lines.append(f"- {prompt['title']} [{prompt['type']}]")
            lines.append(prompt["content"])
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    else:
        lines.append("No prompt templates stored yet.")

    return "\n".join(lines)


def _serialize_log(log: SessionLog) -> dict:
    return {
        "id": log.id,
        "source": log.source,
        "task": log.task,
        "summary": log.summary,
        "actions_taken": log.actions_taken,
        "files_touched": log.files_touched,
        "blockers": log.blockers,
        "next_step": log.next_step,
        "tags": log.tags,
        "created_at": format_datetime(log.created_at),
    }


def _serialize_prompt(prompt: PromptTemplate) -> dict:
    return {
        "id": prompt.id,
        "type": prompt.type,
        "title": prompt.title,
        "content": prompt.content,
        "created_at": format_datetime(prompt.created_at),
        "updated_at": format_datetime(prompt.updated_at),
    }


def _serialize_snapshot(snapshot: Snapshot | None) -> dict | None:
    if snapshot is None:
        return None

    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "content": snapshot.content,
        "created_at": format_datetime(snapshot.created_at),
        "updated_at": format_datetime(snapshot.updated_at),
    }


def _unique_strings(values) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if not value:
            continue
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            items.append(cleaned)
    return items
