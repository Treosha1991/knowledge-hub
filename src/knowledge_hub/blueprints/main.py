from __future__ import annotations

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import distinct, func, select

from ..db import get_session
from ..models import Project, PromptTemplate, SessionLog, Snapshot, User, Workspace, WorkspaceMembership
from ..services import (
    build_deploy_env_status,
    build_deploy_readiness,
    build_deploy_setup_guide,
    build_gpt_actions_setup_guide,
    create_backup_archive,
    get_latest_backup,
    get_mail_status,
    get_inbox_status,
    get_inbox_watcher_status,
    list_knowledge_hub_scheduler_tasks,
    list_latest_handoffs,
    list_recent_backups,
    list_recent_automation_events,
    process_inbox,
    refresh_project_export_bundles,
    safe_record_automation_event,
    safe_record_events_for_projects,
)


bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    session = get_session()
    workspace_ids = sorted(getattr(g, "accessible_workspace_ids", set()))
    include_global_events = g.current_actor.email.lower() == current_app.config["DEFAULT_OWNER_EMAIL"].strip().lower()

    workspace_count = len(getattr(g, "accessible_workspaces", []))
    user_count = session.scalar(
        select(func.count(distinct(WorkspaceMembership.user_id))).where(WorkspaceMembership.workspace_id.in_(workspace_ids))
    ) if workspace_ids else 0
    membership_count = session.scalar(
        select(func.count(WorkspaceMembership.id)).where(WorkspaceMembership.workspace_id.in_(workspace_ids))
    ) if workspace_ids else 0
    project_count = session.scalar(select(func.count(Project.id)).where(Project.workspace_id.in_(workspace_ids))) if workspace_ids else 0
    session_log_count = session.scalar(
        select(func.count(SessionLog.id))
        .join(Project, SessionLog.project_id == Project.id)
        .where(Project.workspace_id.in_(workspace_ids))
    ) if workspace_ids else 0
    prompt_count = session.scalar(
        select(func.count(PromptTemplate.id))
        .join(Project, PromptTemplate.project_id == Project.id)
        .where(Project.workspace_id.in_(workspace_ids))
    ) if workspace_ids else 0
    snapshot_count = session.scalar(
        select(func.count(Snapshot.id))
        .join(Project, Snapshot.project_id == Project.id)
        .where(Project.workspace_id.in_(workspace_ids))
    ) if workspace_ids else 0

    recent_projects = session.scalars(
        select(Project)
        .where(Project.workspace_id.in_(workspace_ids))
        .order_by(Project.updated_at.desc())
        .limit(5)
    ).all()
    recent_logs = session.scalars(
        select(SessionLog)
        .join(Project, SessionLog.project_id == Project.id)
        .where(Project.workspace_id.in_(workspace_ids))
        .order_by(SessionLog.created_at.desc())
        .limit(5)
    ).all()

    return render_template(
        "home.html",
        page_title="Knowledge Hub",
        workspace_count=workspace_count,
        user_count=user_count,
        membership_count=membership_count,
        project_count=project_count,
        session_log_count=session_log_count,
        prompt_count=prompt_count,
        snapshot_count=snapshot_count,
        default_workspace=g.accessible_workspaces[0] if getattr(g, "accessible_workspaces", []) else None,
        default_owner=g.current_actor,
        recent_projects=recent_projects,
        recent_logs=recent_logs,
        recent_handoffs=list_latest_handoffs(
            session,
            current_app.config,
            limit=5,
            accessible_workspace_ids=workspace_ids,
        ),
        recent_automation_events=list_recent_automation_events(
            session,
            limit=8,
            accessible_workspace_ids=workspace_ids,
            include_global=include_global_events,
        ),
        inbox_status=get_inbox_status(current_app.config),
        inbox_watcher_status=get_inbox_watcher_status(current_app.config),
        scheduler_tasks=list_knowledge_hub_scheduler_tasks(current_app.config),
        latest_backup=get_latest_backup(current_app.config),
        recent_backups=list_recent_backups(current_app.config, limit=5),
        deploy_env_status=build_deploy_env_status(current_app.config),
        deploy_readiness=build_deploy_readiness(current_app.config),
        mail_status=get_mail_status(current_app.config, limit=3),
    )


@bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@bp.get("/deploy-readiness")
def deploy_readiness():
    return render_template(
        "deploy_readiness.html",
        page_title="Deploy Readiness",
        readiness=build_deploy_readiness(current_app.config),
    )


@bp.get("/deploy-env")
def deploy_env():
    return render_template(
        "deploy_env_status.html",
        page_title="Deploy Env Status",
        env_status=build_deploy_env_status(current_app.config),
    )


@bp.get("/deploy-setup")
def deploy_setup():
    return render_template(
        "deploy_setup.html",
        page_title="Deploy Setup",
        setup=build_deploy_setup_guide(current_app.config),
    )


@bp.get("/gpt-actions/setup")
def gpt_actions_setup():
    return render_template(
        "gpt_actions_setup.html",
        page_title="GPT Actions Setup",
        setup=build_gpt_actions_setup_guide(current_app.config),
    )


@bp.post("/ops/process-inbox")
def process_inbox_now():
    session = get_session()
    raw_limit = request.form.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else None
    summary = process_inbox(session, current_app.config, limit=limit)
    safe_record_automation_event(
        session,
        event_type="inbox_process_run",
        source="ui",
        message=(
            f"Processed inbox. Scanned {summary.scanned_count}, "
            f"succeeded {summary.success_count}, failed {summary.failed_count}."
        ),
        details=summary.to_dict(),
    )
    flash(
        f"Inbox processed. Scanned {summary.scanned_count}, "
        f"succeeded {summary.success_count}, failed {summary.failed_count}.",
        "success",
    )
    return redirect(url_for("main.home"))


@bp.post("/ops/rebuild-exports-all")
def rebuild_exports_all():
    session = get_session()
    project_slugs = session.scalars(select(Project.slug).order_by(Project.slug.asc())).all()
    export_paths = refresh_project_export_bundles(session, current_app.config, project_slugs)
    safe_record_events_for_projects(
        session,
        project_slugs=project_slugs,
        event_type="exports_rebuild",
        source="ui",
        message=f"Rebuilt export bundle for {len(export_paths)} project(s).",
        details={"rebuilt_count": len(export_paths)},
        log_global_if_empty=True,
    )
    flash(f"Rebuilt exports for {len(export_paths)} project(s).", "success")
    return redirect(url_for("main.home"))


@bp.post("/ops/create-backup")
def create_backup_now():
    session = get_session()
    result = create_backup_archive(current_app.config)
    safe_record_automation_event(
        session,
        event_type="backup_create",
        source="ui",
        message=f"Created backup archive {result.archive.filename}.",
        details=result.to_dict(),
    )
    flash(f"Backup archive created: {result.archive.filename}", "success")
    return redirect(url_for("main.home"))
