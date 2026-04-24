from __future__ import annotations

from flask import Blueprint, Response, current_app, abort, g, jsonify, request
from sqlalchemy import func, select

from ..db import get_session
from ..models import Project, Workspace
from ..services import (
    SessionImportError,
    build_assistant_ready_pack,
    build_chat_bootstrap_pack,
    build_context_pack,
    build_deploy_env_status,
    build_deploy_readiness,
    build_deploy_setup_guide,
    build_gpt_actions_schema,
    build_gpt_actions_setup_guide,
    build_ready_for_next_chat,
    build_manual_prompt_payload,
    build_manual_session_payload,
    build_manual_snapshot_payload,
    get_project_for_actor,
    get_workspace_for_actor,
    create_backup_archive,
    get_latest_backup,
    get_mail_status,
    get_inbox_status,
    get_inbox_watcher_status,
    import_project_package,
    import_prompt_template_payload,
    import_session_payload,
    import_snapshot_payload,
    list_accessible_workspaces,
    list_workspace_memberships,
    list_knowledge_hub_scheduler_tasks,
    list_latest_handoffs,
    list_recent_backups,
    list_recent_automation_events,
    parse_json_text,
    process_inbox,
    refresh_project_export_bundles,
    require_workspace_role,
    render_assistant_ready_text,
    render_chat_bootstrap_text,
    render_context_pack_text,
    safe_record_automation_event,
    safe_record_events_for_projects,
    serialize_api_token,
    upsert_workspace_membership,
)


bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@bp.get("/actor")
def actor():
    return jsonify(
        {
            "ok": True,
            "actor": {
                "id": g.current_actor.id,
                "email": g.current_actor.email,
                "display_name": g.current_actor.display_name,
                "status": g.current_actor.status,
                "source": getattr(g, "current_actor_source", None),
            },
            "api_token": serialize_api_token(g.current_api_token) if getattr(g, "current_api_token", None) else None,
            "accessible_workspace_ids": sorted(getattr(g, "accessible_workspace_ids", set())),
        }
    )


@bp.get("/mail/status")
def mail_status():
    return jsonify({"ok": True, **get_mail_status(current_app.config, limit=5)})


@bp.get("/inbox/status")
def inbox_status():
    return jsonify(get_inbox_status(current_app.config))


@bp.get("/inbox/watcher-status")
def inbox_watcher_status():
    return jsonify({"ok": True, **get_inbox_watcher_status(current_app.config)})


@bp.post("/inbox/process")
def process_inbox_api():
    db_session = get_session()
    raw_limit = request.args.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else None
    summary = process_inbox(db_session, current_app.config, limit=limit)
    return jsonify({"ok": True, **summary.to_dict()})


@bp.get("/handoffs/latest")
def latest_handoffs():
    db_session = get_session()
    raw_limit = request.args.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 8
    return jsonify(
        {
            "ok": True,
            "handoffs": list_latest_handoffs(
                db_session,
                current_app.config,
                limit=limit,
                accessible_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
            ),
        }
    )


@bp.get("/automation-events/latest")
def latest_automation_events():
    db_session = get_session()
    raw_limit = request.args.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 10
    include_global_events = g.current_actor.email.lower() == current_app.config["DEFAULT_OWNER_EMAIL"].strip().lower()
    return jsonify(
        {
            "ok": True,
            "events": list_recent_automation_events(
                db_session,
                limit=limit,
                accessible_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
                include_global=include_global_events,
            ),
        }
    )


@bp.get("/workspaces")
def workspaces():
    db_session = get_session()
    workspaces = list_accessible_workspaces(db_session, g.current_actor)
    return jsonify(
        {
            "ok": True,
            "default_workspace_slug": workspaces[0].slug if workspaces else None,
            "workspaces": [
                _serialize_workspace_summary(db_session, workspace)
                for workspace in workspaces
            ],
        }
    )


@bp.get("/workspaces/<slug>")
def workspace_detail(slug: str):
    db_session = get_session()
    workspace = get_workspace_for_actor(db_session, g.current_actor, slug)
    if workspace is None:
        abort(404)

    memberships = list_workspace_memberships(db_session, workspace)
    projects = db_session.scalars(
        select(Project).where(Project.workspace_id == workspace.id).order_by(Project.updated_at.desc(), Project.slug.asc())
    ).all()

    return jsonify(
        {
            "ok": True,
            "workspace": _serialize_workspace_summary(db_session, workspace),
            "members": [_serialize_workspace_membership(item) for item in memberships],
            "projects": [
                {
                    "id": project.id,
                    "slug": project.slug,
                    "name": project.name,
                    "status": project.status,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                }
                for project in projects
            ],
        }
    )


@bp.get("/workspaces/<slug>/members")
def workspace_members(slug: str):
    db_session = get_session()
    workspace = get_workspace_for_actor(db_session, g.current_actor, slug)
    if workspace is None:
        abort(404)

    memberships = list_workspace_memberships(db_session, workspace)
    return jsonify(
        {
            "ok": True,
            "workspace": _serialize_workspace_summary(db_session, workspace),
            "members": [_serialize_workspace_membership(item) for item in memberships],
        }
    )


@bp.post("/workspaces/<slug>/members")
def add_workspace_member(slug: str):
    db_session = get_session()
    workspace = get_workspace_for_actor(db_session, g.current_actor, slug)
    if workspace is None:
        abort(404)

    try:
        require_workspace_role(db_session, workspace, g.current_actor, roles={"owner", "admin"})
        payload = request.get_json(silent=True) if request.is_json else request.form
        user, membership, created = upsert_workspace_membership(
            db_session,
            workspace,
            email=(payload.get("email") or "").strip(),
            display_name=(payload.get("display_name") or "").strip() or None,
            role=(payload.get("role") or "member").strip() or "member",
            commit=True,
        )
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "created": created,
            "workspace": _serialize_workspace_summary(db_session, workspace),
            "membership": _serialize_workspace_membership(membership),
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "status": user.status,
            },
        }
    )


@bp.get("/scheduler/tasks")
def scheduler_tasks():
    return jsonify(
        {
            "ok": True,
            "tasks": list_knowledge_hub_scheduler_tasks(current_app.config),
        }
    )


@bp.get("/deploy/readiness")
def deploy_readiness():
    return jsonify({"ok": True, **build_deploy_readiness(current_app.config)})


@bp.get("/deploy/env-status")
def deploy_env_status():
    return jsonify({"ok": True, **build_deploy_env_status(current_app.config)})


@bp.get("/deploy/setup")
def deploy_setup():
    return jsonify({"ok": True, **build_deploy_setup_guide(current_app.config)})


@bp.get("/gpt-actions/openapi.json")
def gpt_actions_openapi():
    server_url = current_app.config.get("PUBLIC_BASE_URL") or request.url_root.rstrip("/")
    return jsonify(build_gpt_actions_schema(current_app.config, server_url=server_url))


@bp.get("/gpt-actions/setup")
def gpt_actions_setup_api():
    server_url = current_app.config.get("PUBLIC_BASE_URL") or request.url_root.rstrip("/")
    return jsonify({"ok": True, **build_gpt_actions_setup_guide(current_app.config, server_url=server_url)})


@bp.get("/backups/latest")
def backups_latest():
    raw_limit = request.args.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 5
    return jsonify(
        {
            "ok": True,
            "latest_backup": get_latest_backup(current_app.config),
            "recent_backups": list_recent_backups(current_app.config, limit=limit),
        }
    )


@bp.post("/backups/create")
def create_backup_api():
    db_session = get_session()
    result = create_backup_archive(current_app.config)
    safe_record_automation_event(
        db_session,
        event_type="backup_create",
        source="api",
        message=f"Created backup archive {result.archive.filename}.",
        details=result.to_dict(),
    )
    return jsonify({"ok": True, **result.to_dict()})


@bp.post("/session-logs/import")
def import_session_logs_api():
    db_session = get_session()
    try:
        auto_create_project = _auto_create_flag()
        fallback_project_id = _fallback_project_id()
        fallback_project_slug = request.args.get("project_slug", "").strip() or None
        fallback_workspace_id = _fallback_workspace_id() or _default_accessible_workspace_id()
        fallback_workspace_slug = request.args.get("workspace_slug", "").strip() or None

        payload = _load_request_payload(build_manual_session_payload)
        if not fallback_project_slug:
            fallback_project_slug = request.form.get("project_slug", "").strip() or None
        if not fallback_workspace_slug:
            fallback_workspace_slug = request.form.get("workspace_slug", "").strip() or None

        result = import_session_payload(
            db_session,
            payload,
            fallback_project_id=fallback_project_id,
            fallback_project_slug=fallback_project_slug,
            fallback_workspace_id=fallback_workspace_id,
            fallback_workspace_slug=fallback_workspace_slug,
            auto_create_project=auto_create_project,
            config=current_app.config,
            allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
        )
        export_paths = refresh_project_export_bundles(
            db_session,
            current_app.config,
            [log.project.slug for log in result.logs + result.skipped_logs],
        )
        safe_record_events_for_projects(
            db_session,
            project_slugs=[log.project.slug for log in result.logs + result.skipped_logs],
            event_type="session_log_import",
            source="api",
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
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "imported_count": result.imported_count,
            "skipped_duplicates": result.skipped_count,
            "projects_created": [
                {"id": project.id, "slug": project.slug, "name": project.name}
                for project in result.projects_created
            ],
            "logs": [
                {
                    "id": log.id,
                    "project_id": log.project_id,
                    "source": log.source,
                    "task": log.task,
                    "summary": log.summary,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in result.logs
            ],
            "skipped_log_ids": [log.id for log in result.skipped_logs],
            "project_exports": [item.to_dict() for item in export_paths],
        }
    )


@bp.post("/chat-ingest/session")
def chat_ingest_session():
    db_session = get_session()
    try:
        auto_create_project = _auto_create_flag()
        fallback_project_id = _fallback_project_id()
        fallback_project_slug = request.args.get("project_slug", "").strip() or None
        fallback_workspace_id = _fallback_workspace_id() or _default_accessible_workspace_id()
        fallback_workspace_slug = request.args.get("workspace_slug", "").strip() or None

        payload = _normalize_chat_ingest_payload(_load_request_payload(build_manual_session_payload))
        if not fallback_project_slug:
            fallback_project_slug = request.form.get("project_slug", "").strip() or None
        if not fallback_workspace_slug:
            fallback_workspace_slug = request.form.get("workspace_slug", "").strip() or None

        result = import_session_payload(
            db_session,
            payload,
            fallback_project_id=fallback_project_id,
            fallback_project_slug=fallback_project_slug,
            fallback_workspace_id=fallback_workspace_id,
            fallback_workspace_slug=fallback_workspace_slug,
            auto_create_project=auto_create_project,
            config=current_app.config,
            allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
        )
        touched_projects = [log.project.slug for log in result.logs + result.skipped_logs]
        export_paths = refresh_project_export_bundles(
            db_session,
            current_app.config,
            touched_projects,
        )
        project_slug = touched_projects[0] if touched_projects else fallback_project_slug
        safe_record_events_for_projects(
            db_session,
            project_slugs=touched_projects or ([project_slug] if project_slug else []),
            event_type="chat_ingest_session",
            source="api",
            message=(
                f"Chat ingest completed. Imported {result.imported_count}, "
                f"skipped duplicates {result.skipped_count}."
            ),
            details={
                "imported_count": result.imported_count,
                "skipped_duplicates": result.skipped_count,
                "actor_email": g.current_actor.email if getattr(g, "current_actor", None) else None,
                "actor_source": getattr(g, "current_actor_source", None),
                "api_token": serialize_api_token(g.current_api_token) if getattr(g, "current_api_token", None) else None,
            },
            log_global_if_empty=True,
        )
    except SessionImportError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "project_slug": project_slug,
            "imported_count": result.imported_count,
            "skipped_duplicates": result.skipped_count,
            "project_exports": [item.to_dict() for item in export_paths],
            "ready_for_next_chat_url": (
                f"/api/projects/{project_slug}/ready-for-next-chat"
                if project_slug
                else None
            ),
            "ready_for_next_chat_text_url": (
                f"/api/projects/{project_slug}/ready-for-next-chat.txt"
                if project_slug
                else None
            ),
            "log_ids": [log.id for log in result.logs],
            "skipped_log_ids": [log.id for log in result.skipped_logs],
        }
    )


@bp.get("/gpt-actions/projects")
def gpt_actions_projects():
    db_session = get_session()
    workspace_ids = sorted(getattr(g, "accessible_workspace_ids", set()))
    projects = db_session.scalars(
        select(Project)
        .where(Project.workspace_id.in_(workspace_ids))
        .order_by(Project.updated_at.desc(), Project.slug.asc())
    ).all()
    return jsonify(
        {
            "ok": True,
            "projects": [
                {
                    "slug": project.slug,
                    "name": project.name,
                    "workspace_slug": project.workspace.slug if project.workspace is not None else None,
                    "status": project.status,
                    "current_goal": project.current_goal,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                }
                for project in projects
            ],
        }
    )


@bp.get("/gpt-actions/projects/<slug>/ready-for-next-chat")
def gpt_actions_ready_for_next_chat(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    payload = build_ready_for_next_chat(db_session, current_app.config, project)
    return jsonify(payload)


@bp.post("/gpt-actions/session-log")
def gpt_actions_session_log():
    return chat_ingest_session()


@bp.post("/prompt-templates/import")
def import_prompt_templates_api():
    db_session = get_session()
    try:
        auto_create_project = _auto_create_flag()
        fallback_project_id = _fallback_project_id()
        fallback_project_slug = request.args.get("project_slug", "").strip() or None
        fallback_workspace_id = _fallback_workspace_id() or _default_accessible_workspace_id()
        fallback_workspace_slug = request.args.get("workspace_slug", "").strip() or None

        payload = _load_request_payload(build_manual_prompt_payload)
        if not fallback_project_slug:
            fallback_project_slug = request.form.get("project_slug", "").strip() or None
        if not fallback_workspace_slug:
            fallback_workspace_slug = request.form.get("workspace_slug", "").strip() or None

        result = import_prompt_template_payload(
            db_session,
            payload,
            fallback_project_id=fallback_project_id,
            fallback_project_slug=fallback_project_slug,
            fallback_workspace_id=fallback_workspace_id,
            fallback_workspace_slug=fallback_workspace_slug,
            auto_create_project=auto_create_project,
            config=current_app.config,
            allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
        )
        export_paths = refresh_project_export_bundles(
            db_session,
            current_app.config,
            [item.project.slug for item in result.created_items + result.updated_items],
        )
        safe_record_events_for_projects(
            db_session,
            project_slugs=[item.project.slug for item in result.created_items + result.updated_items],
            event_type="prompt_template_import",
            source="api",
            message=(
                f"Prompt template import completed. Created {result.created_count}, "
                f"updated {result.updated_count}."
            ),
            details={
                "created_count": result.created_count,
                "updated_count": result.updated_count,
            },
            log_global_if_empty=True,
        )
    except SessionImportError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "created_count": result.created_count,
            "updated_count": result.updated_count,
            "projects_created": [
                {"id": project.id, "slug": project.slug, "name": project.name}
                for project in result.projects_created
            ],
            "prompt_templates": [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "type": item.type,
                    "title": item.title,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in result.created_items + result.updated_items
            ],
            "project_exports": [item.to_dict() for item in export_paths],
        }
    )


@bp.post("/snapshots/import")
def import_snapshots_api():
    db_session = get_session()
    try:
        auto_create_project = _auto_create_flag()
        fallback_project_id = _fallback_project_id()
        fallback_project_slug = request.args.get("project_slug", "").strip() or None
        fallback_workspace_id = _fallback_workspace_id() or _default_accessible_workspace_id()
        fallback_workspace_slug = request.args.get("workspace_slug", "").strip() or None

        payload = _load_request_payload(build_manual_snapshot_payload)
        if not fallback_project_slug:
            fallback_project_slug = request.form.get("project_slug", "").strip() or None
        if not fallback_workspace_slug:
            fallback_workspace_slug = request.form.get("workspace_slug", "").strip() or None

        result = import_snapshot_payload(
            db_session,
            payload,
            fallback_project_id=fallback_project_id,
            fallback_project_slug=fallback_project_slug,
            fallback_workspace_id=fallback_workspace_id,
            fallback_workspace_slug=fallback_workspace_slug,
            auto_create_project=auto_create_project,
            config=current_app.config,
            allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
        )
        export_paths = refresh_project_export_bundles(
            db_session,
            current_app.config,
            [item.project.slug for item in result.created_items + result.updated_items],
        )
        safe_record_events_for_projects(
            db_session,
            project_slugs=[item.project.slug for item in result.created_items + result.updated_items],
            event_type="snapshot_import",
            source="api",
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
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "created_count": result.created_count,
            "updated_count": result.updated_count,
            "projects_created": [
                {"id": project.id, "slug": project.slug, "name": project.name}
                for project in result.projects_created
            ],
            "snapshots": [
                {
                    "id": item.id,
                    "project_id": item.project_id,
                    "title": item.title,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in result.created_items + result.updated_items
            ],
            "project_exports": [item.to_dict() for item in export_paths],
        }
    )


@bp.post("/project-packages/import")
def import_project_package_api():
    db_session = get_session()
    try:
        payload = _load_request_payload()
        result = import_project_package(
            db_session,
            payload,
            auto_create_project=_auto_create_flag(),
            config=current_app.config,
            allowed_workspace_ids=getattr(g, "accessible_workspace_ids", set()),
        )
        export_paths = refresh_project_export_bundles(
            db_session,
            current_app.config,
            [result.project_slug],
        )
        safe_record_automation_event(
            db_session,
            event_type="project_package_import",
            source="api",
            message=(
                f"Project package import completed. Logs imported {result.session_logs.imported_count}, "
                f"duplicates skipped {result.session_logs.skipped_count}."
            ),
            project_slug=result.project_slug,
            details={
                "session_logs_imported": result.session_logs.imported_count,
                "session_logs_skipped_duplicates": result.session_logs.skipped_count,
                "prompt_templates_created": result.prompt_templates.created_count,
                "prompt_templates_updated": result.prompt_templates.updated_count,
                "snapshots_created": result.snapshots.created_count,
                "snapshots_updated": result.snapshots.updated_count,
            },
        )
    except SessionImportError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "workspace_slug": result.workspace_slug,
            "project_slug": result.project_slug,
            "project_created": result.project_created,
            "session_logs_imported": result.session_logs.imported_count,
            "session_logs_skipped_duplicates": result.session_logs.skipped_count,
            "prompt_templates_created": result.prompt_templates.created_count,
            "prompt_templates_updated": result.prompt_templates.updated_count,
            "snapshots_created": result.snapshots.created_count,
            "snapshots_updated": result.snapshots.updated_count,
            "project_exports": [item.to_dict() for item in export_paths],
        }
    )


@bp.get("/projects/<slug>/context-pack")
def context_pack(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    context = build_context_pack(db_session, project)
    if request.args.get("format") == "text":
        return Response(render_context_pack_text(context), mimetype="text/plain; charset=utf-8")
    return jsonify(context)


@bp.get("/projects/<slug>/context-pack.txt")
def context_pack_text(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    context = build_context_pack(db_session, project)
    return Response(render_context_pack_text(context), mimetype="text/plain; charset=utf-8")


@bp.get("/projects/<slug>/assistant-ready")
def assistant_ready(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    assistant_pack = build_assistant_ready_pack(db_session, project)
    if request.args.get("format") == "text":
        return Response(render_assistant_ready_text(assistant_pack), mimetype="text/plain; charset=utf-8")
    return jsonify(assistant_pack)


@bp.get("/projects/<slug>/assistant-ready.txt")
def assistant_ready_text(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    assistant_pack = build_assistant_ready_pack(db_session, project)
    return Response(render_assistant_ready_text(assistant_pack), mimetype="text/plain; charset=utf-8")


@bp.get("/projects/<slug>/chat-bootstrap")
def chat_bootstrap(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    chat_bootstrap_pack = build_chat_bootstrap_pack(db_session, project)
    if request.args.get("format") == "text":
        return Response(render_chat_bootstrap_text(chat_bootstrap_pack), mimetype="text/plain; charset=utf-8")
    return jsonify(chat_bootstrap_pack)


@bp.get("/projects/<slug>/chat-bootstrap.txt")
def chat_bootstrap_text(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    chat_bootstrap_pack = build_chat_bootstrap_pack(db_session, project)
    return Response(render_chat_bootstrap_text(chat_bootstrap_pack), mimetype="text/plain; charset=utf-8")


@bp.get("/projects/<slug>/ready-for-next-chat")
def ready_for_next_chat(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    payload = build_ready_for_next_chat(db_session, current_app.config, project)
    if request.args.get("format") == "text":
        return Response(payload["text"], mimetype="text/plain; charset=utf-8")
    return jsonify(payload)


@bp.get("/projects/<slug>/ready-for-next-chat.txt")
def ready_for_next_chat_text(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    payload = build_ready_for_next_chat(db_session, current_app.config, project)
    return Response(payload["text"], mimetype="text/plain; charset=utf-8")


@bp.get("/projects/<slug>/automation-events")
def project_automation_events(slug: str):
    db_session = get_session()
    project = get_project_for_actor(db_session, g.current_actor, slug)
    if project is None:
        abort(404)

    raw_limit = request.args.get("limit", "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 10
    return jsonify(
        {
            "ok": True,
            "project_slug": slug,
            "events": list_recent_automation_events(db_session, project_slug=slug, limit=limit),
        }
    )


def _auto_create_flag() -> bool:
    query_value = request.args.get("auto_create_project")
    if query_value is not None:
        return str(query_value).strip().lower() not in {"0", "false", "no", "off"}

    form_values = request.form.getlist("auto_create_project")
    if form_values:
        normalized = [str(value).strip().lower() for value in form_values]
        return any(value not in {"0", "false", "no", "off", ""} for value in normalized)

    return True


def _fallback_project_id() -> int | None:
    raw_value = request.args.get("project_id") or request.form.get("project_id")
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _fallback_workspace_id() -> int | None:
    raw_value = request.args.get("workspace_id") or request.form.get("workspace_id")
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _default_accessible_workspace_id() -> int | None:
    workspace_ids = sorted(getattr(g, "accessible_workspace_ids", set()))
    return workspace_ids[0] if workspace_ids else None


def _load_request_payload(manual_builder=None):
    if request.is_json:
        payload = request.get_json(silent=True)
        if payload is None:
            raise SessionImportError("Request body must contain valid JSON.")
        return payload

    raw_json = request.form.get("raw_json", "").strip()
    if raw_json:
        return parse_json_text(raw_json)

    if manual_builder is None:
        raise SessionImportError("This endpoint requires a JSON request body or raw_json form field.")

    return manual_builder(request.form)


def _normalize_chat_ingest_payload(payload):
    if isinstance(payload, dict):
        nested = payload.get("session_log") or payload.get("log")
        if isinstance(nested, dict):
            merged = dict(payload)
            merged.pop("session_log", None)
            merged.pop("log", None)
            merged.update(nested)
            return merged
    return payload


def _serialize_workspace_summary(db_session, workspace: Workspace) -> dict:
    memberships = list_workspace_memberships(db_session, workspace)
    owner_memberships = [item for item in memberships if item.role == "owner"]
    project_count = db_session.scalar(
        select(func.count(Project.id)).where(Project.workspace_id == workspace.id)
    )
    return {
        "id": workspace.id,
        "slug": workspace.slug,
        "name": workspace.name,
        "description": workspace.description,
        "plan": workspace.plan,
        "status": workspace.status,
        "project_count": project_count or 0,
        "member_count": len(memberships),
        "owner_count": len(owner_memberships),
        "owners": [
            {
                "id": item.user.id,
                "email": item.user.email,
                "display_name": item.user.display_name,
            }
            for item in owner_memberships
        ],
    }


def _serialize_workspace_membership(item) -> dict:
    return {
        "id": item.id,
        "role": item.role,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "user": {
            "id": item.user.id,
            "email": item.user.email,
            "display_name": item.user.display_name,
            "status": item.user.status,
        },
    }
