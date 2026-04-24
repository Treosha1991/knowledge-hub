from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import select

from ..db import get_session
from ..models import Project, Snapshot
from ..services import (
    SessionImportError,
    build_manual_snapshot_payload,
    get_default_accessible_workspace,
    get_project_for_actor,
    import_snapshot_payload,
    list_accessible_workspaces,
    scope_project_statement,
    parse_json_text,
    refresh_project_export_bundles,
    safe_record_events_for_projects,
)


bp = Blueprint("snapshots", __name__, url_prefix="/snapshots")


@bp.get("/")
def index():
    session = get_session()
    project_slug = request.args.get("project", "").strip()
    project = None

    statement = (
        select(Snapshot)
        .join(Project, Snapshot.project_id == Project.id)
        .where(Project.workspace_id.in_(sorted(getattr(g, "accessible_workspace_ids", set()))))
        .order_by(Snapshot.updated_at.desc())
    )
    if project_slug:
        project = get_project_for_actor(session, g.current_actor, project_slug)
        if project is not None:
            statement = (
                select(Snapshot)
                .where(Snapshot.project_id == project.id)
                .order_by(Snapshot.updated_at.desc())
            )
        else:
            abort(404)

    snapshots = session.scalars(statement.limit(50)).all()
    return render_template(
        "snapshots/index.html",
        page_title="Snapshots",
        snapshots=snapshots,
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
        flash("Create or join a workspace first before saving snapshots.", "info")
        return redirect(url_for("workspaces.create"))
    form_data = {
        "project_id": "",
        "workspace_id": str(default_workspace.id),
        "workspace_slug": "",
        "workspace_name": "",
        "project_slug": request.args.get("project", "").strip(),
        "project_name": "",
        "title": "",
        "content": "",
        "raw_json": "",
        "auto_create_project": "1",
    }
    errors: list[str] = []

    if request.method == "POST":
        form_data = {key: request.form.get(key, "") for key in form_data}
        auto_create_project = "1" in request.form.getlist("auto_create_project")
        form_data["auto_create_project"] = "1" if auto_create_project else "0"
        fallback_project_id = int(form_data["project_id"]) if form_data["project_id"].isdigit() else None
        fallback_workspace_id = int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id
        fallback_project_slug = form_data["project_slug"].strip() or None

        try:
            payload = parse_json_text(form_data["raw_json"]) if form_data["raw_json"].strip() else build_manual_snapshot_payload(request.form)
            result = import_snapshot_payload(
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
                [item.project.slug for item in result.created_items + result.updated_items],
            )
            safe_record_events_for_projects(
                db_session,
                project_slugs=[item.project.slug for item in result.created_items + result.updated_items],
                event_type="snapshot_import",
                source="ui",
                message=(
                    f"Snapshot import completed. Created {result.created_count}, "
                    f"updated {result.updated_count}."
                ),
                details={
                    "created_count": result.created_count,
                    "updated_count": result.updated_count,
                },
                log_global_if_empty=True,
            )
        except SessionImportError as exc:
            errors.append(str(exc))
            flash("Snapshot import failed. Fix the payload and try again.", "error")
        else:
            target_project = None
            if result.created_items:
                target_project = result.created_items[0].project
            elif result.updated_items:
                target_project = result.updated_items[0].project

            flash(
                f"Snapshots saved. Created: {result.created_count}, updated: {result.updated_count}.",
                "success",
            )
            if target_project is not None:
                return redirect(url_for("projects.detail", slug=target_project.slug))
            return redirect(url_for("snapshots.index"))

    return render_template(
        "snapshots/new.html",
        page_title="New Snapshot",
        projects=projects,
        workspaces=workspaces,
        project_slug=form_data["project_slug"],
        selected_project_id=int(form_data["project_id"]) if form_data["project_id"].isdigit() else None,
        selected_workspace_id=int(form_data["workspace_id"]) if form_data["workspace_id"].isdigit() else default_workspace.id,
        form_data=form_data,
        errors=errors,
        sample_json=_sample_json(),
        import_api_url=url_for("api.import_snapshots_api", _external=True),
    )


def _sample_json() -> str:
    return """{
  "project_slug": "automation-lab",
  "title": "Current project state",
  "content": "Knowledge Hub already supports session log import, context pack generation, and API export for reuse in new chats."
}"""
