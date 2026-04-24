from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import get_session
from ..models import Project, PromptTemplate, SessionLog, Snapshot, Workspace
from ..services import (
    build_assistant_ready_pack,
    build_chat_bootstrap_pack,
    build_context_pack,
    build_ready_for_next_chat,
    find_duplicate_session_log_groups,
    get_default_accessible_workspace,
    get_project_for_actor,
    get_workspace_for_actor,
    get_project_export_paths,
    list_accessible_workspaces,
    list_recent_automation_events,
    refresh_project_export_bundle,
    run_session_log_dedupe,
    safe_record_automation_event,
    scope_project_statement,
    render_assistant_ready_text,
    render_chat_bootstrap_text,
    render_context_pack_text,
)
from ..utils import blank_to_none, slugify


bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.get("/")
def index():
    session = get_session()
    workspace_slug = request.args.get("workspace", "").strip()
    workspace = None
    statement = scope_project_statement(select(Project), getattr(g, "accessible_workspace_ids", set())).order_by(Project.updated_at.desc())
    if workspace_slug:
        workspace = get_workspace_for_actor(session, g.current_actor, workspace_slug)
        if workspace is not None:
            statement = (
                select(Project)
                .where(Project.workspace_id == workspace.id)
                .order_by(Project.updated_at.desc())
            )
        else:
            abort(404)
    projects = session.scalars(statement).all()
    return render_template(
        "projects/index.html",
        page_title="Projects",
        projects=projects,
        workspace=workspace,
        workspace_slug=workspace_slug,
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    session = get_session()
    default_workspace = get_default_accessible_workspace(session, g.current_actor, current_app.config)
    workspaces = list_accessible_workspaces(session, g.current_actor)
    if default_workspace is None:
        flash("Create a workspace first before creating projects.", "info")
        return redirect(url_for("workspaces.create"))
    form_data = {
        "workspace_id": str(default_workspace.id),
        "name": "",
        "slug": "",
        "description": "",
        "stack": "",
        "status": "active",
        "current_goal": "",
        "rules": "",
    }
    errors: list[str] = []

    if request.method == "POST":
        form_data = {key: request.form.get(key, "") for key in form_data}

        workspace_id = int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id
        name = form_data["name"].strip()
        slug = slugify(form_data["slug"].strip() or name)
        description = blank_to_none(form_data["description"])
        stack = blank_to_none(form_data["stack"])
        status = form_data["status"].strip() or "active"
        current_goal = blank_to_none(form_data["current_goal"])
        rules = blank_to_none(form_data["rules"])

        if not name:
            errors.append("Project name is required.")
        if not slug:
            errors.append("Project slug is required.")
        existing = session.scalar(select(Project).where(Project.slug == slug))
        if existing is not None:
            errors.append("Project slug must be unique.")
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            errors.append("Select a valid workspace.")
        elif workspace.id not in getattr(g, "accessible_workspace_ids", set()):
            errors.append("You do not have access to that workspace.")

        if not errors:
            project = Project(
                workspace_id=workspace_id,
                name=name,
                slug=slug,
                description=description,
                stack=stack,
                status=status,
                current_goal=current_goal,
                rules=rules,
            )
            session.add(project)
            session.commit()
            refresh_project_export_bundle(session, current_app.config, project)
            safe_record_automation_event(
                session,
                event_type="project_create",
                source="ui",
                message=f"Created project '{project.name}'.",
                project=project,
                details={"project_slug": project.slug},
            )
            flash("Project created successfully.", "success")
            return redirect(url_for("projects.detail", slug=project.slug))

        flash("Fix the validation issues and try again.", "error")

    return render_template(
        "projects/new.html",
        page_title="New Project",
        workspaces=workspaces,
        selected_workspace_id=int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id,
        form_data=form_data,
        errors=errors,
    )


@bp.get("/<slug>")
def detail(slug: str):
    session = get_session()
    project = get_project_for_actor(session, g.current_actor, slug)
    if project is None:
        abort(404)

    recent_logs = session.scalars(
        select(SessionLog)
        .where(SessionLog.project_id == project.id)
        .order_by(SessionLog.created_at.desc())
        .limit(5)
    ).all()
    recent_prompts = session.scalars(
        select(PromptTemplate)
        .where(PromptTemplate.project_id == project.id)
        .order_by(PromptTemplate.updated_at.desc())
        .limit(5)
    ).all()
    recent_snapshots = session.scalars(
        select(Snapshot)
        .where(Snapshot.project_id == project.id)
        .order_by(Snapshot.updated_at.desc())
        .limit(5)
    ).all()

    next_step = next((log.next_step for log in recent_logs if log.next_step), None)
    chat_bootstrap_pack = build_chat_bootstrap_pack(session, project)
    assistant_ready_pack = build_assistant_ready_pack(session, project)
    context_pack = build_context_pack(session, project)
    export_paths = get_project_export_paths(current_app.config, project.slug)
    recent_automation_events = list_recent_automation_events(session, project_slug=project.slug, limit=6)
    duplicate_groups = find_duplicate_session_log_groups(session, [project])

    return render_template(
        "projects/detail.html",
        page_title=project.name,
        project=project,
        recent_logs=recent_logs,
        recent_prompts=recent_prompts,
        recent_snapshots=recent_snapshots,
        next_step=next_step,
        chat_bootstrap_pack=chat_bootstrap_pack,
        chat_bootstrap_text=render_chat_bootstrap_text(chat_bootstrap_pack),
        assistant_ready_pack=assistant_ready_pack,
        assistant_ready_text=render_assistant_ready_text(assistant_ready_pack),
        context_pack=context_pack,
        context_pack_text=render_context_pack_text(context_pack),
        export_paths=export_paths,
        recent_automation_events=recent_automation_events,
        duplicate_group_count=len(duplicate_groups),
        duplicate_log_count=sum(len(item["remove_log_ids"]) for item in duplicate_groups),
    )


@bp.get("/<slug>/handoff")
def handoff_page(slug: str):
    session = get_session()
    project = get_project_for_actor(session, g.current_actor, slug)
    if project is None:
        abort(404)

    handoff = build_ready_for_next_chat(session, current_app.config, project)
    return render_template(
        "projects/handoff.html",
        page_title=f"{project.name} Handoff",
        project=project,
        handoff=handoff,
    )


@bp.post("/<slug>/ops/rebuild-exports")
def rebuild_exports(slug: str):
    session = get_session()
    project = get_project_for_actor(session, g.current_actor, slug)
    if project is None:
        abort(404)

    refresh_project_export_bundle(session, current_app.config, project)
    safe_record_automation_event(
        session,
        event_type="exports_rebuild",
        source="ui",
        message=f"Rebuilt export bundle for '{project.slug}'.",
        project=project,
        details={"project_slug": project.slug},
    )
    flash("Project exports rebuilt.", "success")
    return redirect(url_for("projects.detail", slug=slug))


@bp.post("/<slug>/ops/dedupe-dry-run")
def dedupe_dry_run(slug: str):
    session = get_session()
    project = get_project_for_actor(session, g.current_actor, slug)
    if project is None:
        abort(404)

    result = run_session_log_dedupe(session, current_app.config, [project], apply=False)
    safe_record_automation_event(
        session,
        event_type="session_log_dedupe",
        source="ui",
        message=(
            f"Dedupe dry run for '{project.slug}'. "
            f"Groups: {result.duplicate_groups}, duplicate logs: {result.duplicate_logs}."
        ),
        project=project,
        details={
            "mode": "dry_run",
            "duplicate_groups": result.duplicate_groups,
            "duplicate_logs": result.duplicate_logs,
        },
    )
    flash(
        f"Dedupe dry run found {result.duplicate_groups} duplicate group(s) "
        f"and {result.duplicate_logs} removable log(s).",
        "info",
    )
    return redirect(url_for("projects.detail", slug=slug))


@bp.post("/<slug>/ops/dedupe-apply")
def dedupe_apply(slug: str):
    session = get_session()
    project = get_project_for_actor(session, g.current_actor, slug)
    if project is None:
        abort(404)

    result = run_session_log_dedupe(session, current_app.config, [project], apply=True)
    safe_record_automation_event(
        session,
        event_type="session_log_dedupe",
        source="ui",
        message=(
            f"Dedupe apply for '{project.slug}'. "
            f"Removed {result.removed_logs} duplicate session log(s)."
        ),
        project=project,
        details={
            "mode": "apply",
            "duplicate_groups": result.duplicate_groups,
            "removed_logs": result.removed_logs,
        },
    )
    flash(
        f"Dedupe complete. Removed {result.removed_logs} duplicate session log(s).",
        "success",
    )
    return redirect(url_for("projects.detail", slug=slug))
