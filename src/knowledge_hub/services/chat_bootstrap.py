from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Project, PromptTemplate, SessionLog, Snapshot
from ..utils import format_datetime
from .log_dedup import unique_logs_by_meaning


def build_chat_bootstrap_pack(
    db_session: Session,
    project: Project,
    *,
    log_limit: int = 3,
    prompt_limit: int = 3,
    file_limit: int = 4,
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

    latest_log = recent_logs[0] if recent_logs else None
    blockers = _unique_strings(latest_log.blockers if latest_log is not None else [])
    next_steps = _unique_strings(log.next_step for log in recent_logs if log.next_step)
    key_files = _unique_strings(item for log in recent_logs for item in log.files_touched)[:file_limit]
    recent_tags = _unique_strings(item for log in recent_logs for item in log.tags)
    selected_prompt = _pick_prompt_template(recent_prompts)
    recent_decisions = _unique_recent_decisions(recent_logs)

    pack = {
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
            "current_goal": project.current_goal,
            "recommended_next_step": next_steps[0] if next_steps else project.current_goal,
            "active_blockers": blockers[:3],
            "recent_tags": recent_tags[:5],
            "key_files": key_files,
        },
        "latest_snapshot": _serialize_snapshot(latest_snapshot),
        "recent_decisions": recent_decisions,
        "starter_template": _serialize_prompt(selected_prompt),
    }
    pack["bootstrap_text"] = _render_bootstrap_text(pack)
    return pack


def render_chat_bootstrap_text(chat_bootstrap_pack: dict) -> str:
    return chat_bootstrap_pack["bootstrap_text"]


def _render_bootstrap_text(chat_bootstrap_pack: dict) -> str:
    project = chat_bootstrap_pack["project"]
    focus = chat_bootstrap_pack["focus"]
    latest_snapshot = chat_bootstrap_pack["latest_snapshot"]
    decisions = chat_bootstrap_pack["recent_decisions"]
    starter_template = chat_bootstrap_pack["starter_template"]

    lines = [
        f"You are joining ongoing work on the project '{project['name']}' ({project['slug']}).",
        f"Current goal: {focus['current_goal'] or 'Not set.'}",
        f"Recommended next step: {focus['recommended_next_step'] or 'Not captured yet.'}",
    ]

    if focus["active_blockers"]:
        lines.append(f"Active blockers: {', '.join(focus['active_blockers'])}.")
    else:
        lines.append("Active blockers: none recorded.")

    if project["rules"]:
        lines.append(f"Project rules: {project['rules']}")
    else:
        lines.append("Project rules: no special rules captured yet.")

    if latest_snapshot is not None and latest_snapshot["content"]:
        lines.append(f"Latest snapshot: {latest_snapshot['content']}")

    if decisions:
        lines.append("Recent decisions:")
        for item in decisions:
            summary = item["summary"] or item["task"] or "No summary recorded."
            lines.append(f"- {summary}")

    if focus["key_files"]:
        lines.append(f"Key files touched recently: {', '.join(focus['key_files'])}.")

    if starter_template is not None:
        lines.append(f"Preferred chat instruction: {starter_template['content']}")
    else:
        lines.append("Preferred chat instruction: Continue from this context and propose the next practical step.")

    lines.append("Do not ask to restate the basic context. Continue from this state and move the work forward.")
    return "\n".join(lines)


def _pick_prompt_template(prompts: list[PromptTemplate]) -> PromptTemplate | None:
    if not prompts:
        return None
    for prompt in prompts:
        if prompt.type == "new_chat":
            return prompt
    return prompts[0]


def _serialize_decision(log: SessionLog) -> dict:
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


def _unique_recent_decisions(logs: list[SessionLog]) -> list[dict]:
    return [_serialize_decision(log) for log in unique_logs_by_meaning(logs)]
