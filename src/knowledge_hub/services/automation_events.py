from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import AutomationEvent, Project
from ..utils import format_datetime


def record_automation_event(
    db_session: Session,
    *,
    event_type: str,
    source: str,
    message: str,
    status: str = "success",
    project: Project | None = None,
    project_slug: str | None = None,
    details: dict | None = None,
    commit: bool = True,
) -> AutomationEvent:
    resolved_project = project
    if resolved_project is None and project_slug:
        resolved_project = db_session.scalar(select(Project).where(Project.slug == project_slug))

    event = AutomationEvent(
        project_id=resolved_project.id if resolved_project is not None else None,
        event_type=event_type,
        source=source,
        status=status,
        message=message,
        details=details or {},
    )
    db_session.add(event)

    if commit:
        db_session.commit()
        db_session.refresh(event)
    else:
        db_session.flush()

    return event


def safe_record_automation_event(
    db_session: Session,
    *,
    event_type: str,
    source: str,
    message: str,
    status: str = "success",
    project: Project | None = None,
    project_slug: str | None = None,
    details: dict | None = None,
    commit: bool = True,
) -> AutomationEvent | None:
    try:
        return record_automation_event(
            db_session,
            event_type=event_type,
            source=source,
            message=message,
            status=status,
            project=project,
            project_slug=project_slug,
            details=details,
            commit=commit,
        )
    except Exception:
        db_session.rollback()
        return None


def safe_record_events_for_projects(
    db_session: Session,
    *,
    project_slugs: Iterable[str],
    event_type: str,
    source: str,
    message: str,
    status: str = "success",
    details: dict | None = None,
    log_global_if_empty: bool = False,
) -> list[AutomationEvent]:
    events: list[AutomationEvent] = []
    seen: set[str] = set()

    for project_slug in project_slugs:
        cleaned_slug = str(project_slug or "").strip()
        if not cleaned_slug or cleaned_slug in seen:
            continue
        seen.add(cleaned_slug)
        event = safe_record_automation_event(
            db_session,
            event_type=event_type,
            source=source,
            message=message,
            status=status,
            project_slug=cleaned_slug,
            details=details,
        )
        if event is not None:
            events.append(event)

    if not seen and log_global_if_empty:
        event = safe_record_automation_event(
            db_session,
            event_type=event_type,
            source=source,
            message=message,
            status=status,
            details=details,
        )
        if event is not None:
            events.append(event)

    return events


def list_recent_automation_events(
    db_session: Session,
    *,
    project_slug: str | None = None,
    limit: int = 10,
    accessible_workspace_ids: set[int] | list[int] | None = None,
    include_global: bool = True,
) -> list[dict]:
    statement = (
        select(AutomationEvent)
        .options(selectinload(AutomationEvent.project))
        .order_by(AutomationEvent.created_at.desc(), AutomationEvent.id.desc())
        .limit(max(limit, 0))
    )

    if project_slug:
        statement = (
            select(AutomationEvent)
            .join(Project, AutomationEvent.project_id == Project.id)
            .options(selectinload(AutomationEvent.project))
            .where(Project.slug == project_slug)
            .order_by(AutomationEvent.created_at.desc(), AutomationEvent.id.desc())
            .limit(max(limit, 0))
        )
    elif accessible_workspace_ids is not None:
        workspace_ids = sorted({int(value) for value in accessible_workspace_ids if value is not None})
        if workspace_ids:
            conditions = [Project.workspace_id.in_(workspace_ids)]
            if include_global:
                conditions.append(AutomationEvent.project_id.is_(None))
            statement = (
                select(AutomationEvent)
                .outerjoin(Project, AutomationEvent.project_id == Project.id)
                .options(selectinload(AutomationEvent.project))
                .where(or_(*conditions))
                .order_by(AutomationEvent.created_at.desc(), AutomationEvent.id.desc())
                .limit(max(limit, 0))
            )
        else:
            if include_global:
                statement = (
                    select(AutomationEvent)
                    .where(AutomationEvent.project_id.is_(None))
                    .options(selectinload(AutomationEvent.project))
                    .order_by(AutomationEvent.created_at.desc(), AutomationEvent.id.desc())
                    .limit(max(limit, 0))
                )
            else:
                statement = (
                    select(AutomationEvent)
                    .where(AutomationEvent.id == -1)
                    .options(selectinload(AutomationEvent.project))
                    .limit(0)
                )

    events = db_session.scalars(statement).all()
    return [_serialize_event(item) for item in events]


def _serialize_event(event: AutomationEvent) -> dict:
    project = event.project
    return {
        "id": event.id,
        "event_type": event.event_type,
        "source": event.source,
        "status": event.status,
        "message": event.message,
        "details": event.details or {},
        "created_at": format_datetime(event.created_at),
        "project_slug": project.slug if project is not None else None,
        "project_name": project.name if project is not None else None,
    }
