from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, PromptTemplate, SessionLog, Snapshot
from ..utils import format_datetime
from .log_dedup import unique_logs_by_meaning


def build_assistant_ready_pack(
    db_session: Session,
    project: Project,
    *,
    log_limit: int = 4,
    prompt_limit: int = 3,
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
    latest_snapshot = db_session.scalar(
        select(Snapshot)
        .where(Snapshot.project_id == project.id)
        .order_by(Snapshot.updated_at.desc())
        .limit(1)
    )
    recent_logs = unique_logs_by_meaning(recent_logs)

    blockers = _unique_strings(item for log in recent_logs for item in log.blockers)
    next_steps = _unique_strings(log.next_step for log in recent_logs if log.next_step)
    tags = _unique_strings(item for log in recent_logs for item in log.tags)

    selected_prompt = _pick_prompt_template(recent_prompts)
    recent_notes = _unique_brief_logs(recent_logs)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "slug": project.slug,
            "name": project.name,
            "status": project.status,
            "description": project.description,
            "stack": project.stack,
            "current_goal": project.current_goal,
            "rules": project.rules,
            "updated_at": format_datetime(project.updated_at),
        },
        "focus": {
            "recommended_next_step": next_steps[0] if next_steps else project.current_goal,
            "active_blockers": blockers,
            "recent_tags": tags,
        },
        "latest_snapshot": _serialize_snapshot(latest_snapshot),
        "recent_session_notes": recent_notes,
        "selected_prompt_template": _serialize_prompt(selected_prompt),
    }


def render_assistant_ready_text(assistant_pack: dict) -> str:
    project = assistant_pack["project"]
    focus = assistant_pack["focus"]
    latest_snapshot = assistant_pack["latest_snapshot"]
    session_notes = assistant_pack["recent_session_notes"]
    selected_prompt = assistant_pack["selected_prompt_template"]

    lines = [
        "Assistant-Ready Project Brief",
        f"Generated at: {assistant_pack['generated_at']}",
        "",
        "Project",
        f"- Name: {project['name']}",
        f"- Slug: {project['slug']}",
        f"- Status: {project['status']}",
        f"- Current goal: {project['current_goal'] or 'Not set'}",
        f"- Description: {project['description'] or 'Not set'}",
        f"- Stack: {project['stack'] or 'Not set'}",
        "",
        "Rules",
        project["rules"] or "No rules captured yet.",
        "",
        "Immediate Focus",
        f"- Recommended next step: {focus['recommended_next_step'] or 'Not captured yet'}",
    ]

    if focus["active_blockers"]:
        lines.append(f"- Active blockers: {', '.join(focus['active_blockers'])}")
    else:
        lines.append("- Active blockers: none recorded")

    if focus["recent_tags"]:
        lines.append(f"- Recent tags: {', '.join(focus['recent_tags'])}")
    else:
        lines.append("- Recent tags: none recorded")

    lines.extend(["", "Latest Snapshot"])
    if latest_snapshot is not None:
        lines.append(f"- Title: {latest_snapshot['title']}")
        lines.append(latest_snapshot["content"] or "No content.")
    else:
        lines.append("No snapshot stored yet.")

    lines.extend(["", "Recent Session Notes"])
    if session_notes:
        for note in session_notes:
            lines.append(f"- {note['task'] or 'Untitled session'}")
            if note["summary"]:
                lines.append(f"  Summary: {note['summary']}")
            if note["next_step"]:
                lines.append(f"  Next step: {note['next_step']}")
    else:
        lines.append("No recent session notes.")

    lines.extend(["", "Suggested Chat Instruction"])
    if selected_prompt is not None:
        lines.append(f"- Template: {selected_prompt['title']} [{selected_prompt['type']}]")
        lines.append(selected_prompt["content"])
    else:
        lines.append("Start by reading the project brief, reflect the current goal, and propose the next practical step.")

    return "\n".join(lines)


def _pick_prompt_template(prompts: list[PromptTemplate]) -> PromptTemplate | None:
    if not prompts:
        return None
    for prompt in prompts:
        if prompt.type == "new_chat":
            return prompt
    return prompts[0]


def _serialize_brief_log(log: SessionLog) -> dict:
    return {
        "id": log.id,
        "task": log.task,
        "summary": log.summary,
        "next_step": log.next_step,
        "created_at": format_datetime(log.created_at),
    }


def _serialize_prompt(prompt: PromptTemplate | None) -> dict | None:
    if prompt is None:
        return None
    return {
        "id": prompt.id,
        "type": prompt.type,
        "title": prompt.title,
        "content": prompt.content,
        "updated_at": format_datetime(prompt.updated_at),
    }


def _serialize_snapshot(snapshot: Snapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "content": snapshot.content,
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


def _unique_brief_logs(logs: list[SessionLog]) -> list[dict]:
    return [_serialize_brief_log(log) for log in unique_logs_by_meaning(logs)]
