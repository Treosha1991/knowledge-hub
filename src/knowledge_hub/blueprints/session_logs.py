from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import get_session
from ..models import Project, SessionLog
from ..services import (
    SessionImportError,
    build_manual_session_payload,
    get_default_accessible_workspace,
    get_project_for_actor,
    import_session_payload,
    list_accessible_workspaces,
    scope_project_statement,
    parse_json_text,
    refresh_project_export_bundles,
    safe_record_events_for_projects,
)


bp = Blueprint("session_logs", __name__, url_prefix="/session-logs")


@bp.get("/")
def index():
    session = get_session()
    project_slug = request.args.get("project", "").strip()
    project = None

    statement = (
        select(SessionLog)
        .join(Project, SessionLog.project_id == Project.id)
        .where(Project.workspace_id.in_(sorted(getattr(g, "accessible_workspace_ids", set()))))
        .order_by(SessionLog.created_at.desc())
    )
    if project_slug:
        project = get_project_for_actor(session, g.current_actor, project_slug)
        if project is not None:
            statement = (
                select(SessionLog)
                .where(SessionLog.project_id == project.id)
                .order_by(SessionLog.created_at.desc())
            )
        else:
            abort(404)

    logs = session.scalars(statement.limit(50)).all()
    return render_template(
        "session_logs/index.html",
        page_title="Session Logs",
        logs=logs,
        project=project,
        project_slug=project_slug,
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    db_session = get_session()
    projects = db_session.scalars(
        scope_project_statement(select(Project), getattr(g, "accessible_workspace_ids", set())).order_by(Project.name.asc())
    ).all()
    default_workspace = get_default_accessible_workspace(db_session, g.current_actor, current_app.config)
    workspaces = list_accessible_workspaces(db_session, g.current_actor)
    if default_workspace is None:
        flash("Create or join a workspace first before importing session logs.", "info")
        return redirect(url_for("workspaces.create"))
    form_data = {
        "project_id": "",
        "workspace_id": str(default_workspace.id),
        "workspace_slug": "",
        "workspace_name": "",
        "project_slug": request.args.get("project", "").strip(),
        "project_name": "",
        "source": "chatgpt",
        "task": "",
        "summary": "",
        "actions_taken": "",
        "files_touched": "",
        "blockers": "",
        "next_step": "",
        "tags": "",
        "raw_json": "",
        "auto_create_project": "1",
    }
    errors: list[str] = []

    if request.method == "POST":
        form_data = {key: request.form.get(key, "") for key in form_data}
        raw_json = form_data["raw_json"].strip()
        auto_create_project = "1" in request.form.getlist("auto_create_project")
        form_data["auto_create_project"] = "1" if auto_create_project else "0"
        fallback_project_id = int(form_data["project_id"]) if form_data["project_id"].isdigit() else None
        fallback_workspace_id = int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id
        fallback_project_slug = form_data["project_slug"].strip() or None

        try:
            payload = parse_json_text(raw_json) if raw_json else build_manual_session_payload(request.form)
            result = import_session_payload(
                db_session,
                payload,
                fallback_project_id=fallback_project_id,
                fallback_project_slug=fallback_project_slug,
                fallback_workspace_id=fallback_workspace_id,
                auto_create_project=auto_create_project,
                config=current_app.config,
                allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
            )
            refresh_project_export_bundles(
                db_session,
                current_app.config,
                [log.project.slug for log in result.logs + result.skipped_logs],
            )
            safe_record_events_for_projects(
                db_session,
                project_slugs=[log.project.slug for log in result.logs + result.skipped_logs],
                event_type="session_log_import",
                source="ui",
                message=(
                    f"Session log import completed. Imported {result.imported_count}, "
                    f"skipped duplicates {result.skipped_count}."
                ),
                details={
                    "imported_count": result.imported_count,
                    "skipped_duplicates": result.skipped_count,
                },
                log_global_if_empty=True,
            )
        except SessionImportError as exc:
            errors.append(str(exc))
            flash("Session log import failed. Fix the payload and try again.", "error")
        else:
            if result.imported_count == 1 and result.skipped_count == 0:
                log = result.logs[0]
                flash("Session log imported successfully.", "success")
                return redirect(url_for("projects.detail", slug=log.project.slug))

            if result.imported_count == 0 and result.skipped_count == 1:
                log = result.skipped_logs[0]
                flash("Duplicate session log skipped. Existing project context is unchanged.", "info")
                return redirect(url_for("projects.detail", slug=log.project.slug))

            flash(
                f"Imported {result.imported_count} session logs. Skipped duplicates: {result.skipped_count}.",
                "success",
            )
            return redirect(url_for("session_logs.index"))

    return render_template(
        "session_logs/new.html",
        page_title="New Session Log",
        projects=projects,
        workspaces=workspaces,
        project_slug=form_data["project_slug"],
        selected_project_id=int(form_data["project_id"]) if form_data["project_id"].isdigit() else None,
        selected_workspace_id=int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id,
        form_data=form_data,
        errors=errors,
        sample_json=_sample_json(),
        import_api_url=url_for("api.import_session_logs_api", _external=True),
    )


def _sample_json() -> str:
    return """{
  "project_slug": "knowledge-hub",
  "source": "chatgpt",
  "task": "Design automatic session log import and context pack export",
  "summary": "Chose an automation-first flow: JSON import, API, CLI, and context pack export.",
  "actions_taken": [
    "Designed session log import",
    "Added a dedicated context pack endpoint"
  ],
  "files_touched": [
    "src/knowledge_hub/blueprints/session_logs.py",
    "src/knowledge_hub/services/context_pack.py"
  ],
  "blockers": [],
  "next_step": "Add CLI tools for import and context pack export",
  "tags": ["automation", "knowledge-hub", "api"]
}"""
