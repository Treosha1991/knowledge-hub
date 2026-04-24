from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, select

from ..db import get_session
from ..models import Project, Workspace, WorkspaceMembership
from ..services import (
    get_workspace_for_actor,
    list_workspace_memberships,
    require_workspace_role,
    upsert_workspace_membership,
)
from ..utils import blank_to_none, slugify


bp = Blueprint("workspaces", __name__, url_prefix="/workspaces")


@bp.get("/")
def index():
    session = get_session()
    workspace_ids = sorted(getattr(g, "accessible_workspace_ids", set()))
    workspaces = session.scalars(
        select(Workspace)
        .where(Workspace.id.in_(workspace_ids))
        .order_by(Workspace.name.asc(), Workspace.slug.asc())
    ).all()
    counts = dict(
        session.execute(
            select(Project.workspace_id, func.count(Project.id))
            .group_by(Project.workspace_id)
        ).all()
    )
    member_counts = dict(
        session.execute(
            select(WorkspaceMembership.workspace_id, func.count(WorkspaceMembership.id))
            .group_by(WorkspaceMembership.workspace_id)
        ).all()
    )
    return render_template(
        "workspaces/index.html",
        page_title="Workspaces",
        workspaces=workspaces,
        project_counts=counts,
        member_counts=member_counts,
    )


@bp.get("/<slug>")
def detail(slug: str):
    session = get_session()
    workspace = get_workspace_for_actor(session, g.current_actor, slug)
    if workspace is None:
        abort(404)

    projects = session.scalars(
        select(Project)
        .where(Project.workspace_id == workspace.id)
        .order_by(Project.updated_at.desc(), Project.slug.asc())
    ).all()
    memberships = list_workspace_memberships(session, workspace)
    owner_memberships = [item for item in memberships if item.role == "owner"]
    try:
        require_workspace_role(session, workspace, g.current_actor, roles={"owner", "admin"})
        can_manage_members = True
    except PermissionError:
        can_manage_members = False

    return render_template(
        "workspaces/detail.html",
        page_title=workspace.name,
        workspace=workspace,
        projects=projects,
        memberships=memberships,
        owner_memberships=owner_memberships,
        can_manage_members=can_manage_members,
        member_form_data={"email": "", "display_name": "", "role": "member"},
        member_errors=[],
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    session = get_session()
    form_data = {
        "name": "",
        "slug": "",
        "description": "",
        "plan": "internal",
        "status": "active",
    }
    errors: list[str] = []

    if request.method == "POST":
        form_data = {key: request.form.get(key, "") for key in form_data}
        name = form_data["name"].strip()
        slug = slugify(form_data["slug"].strip() or name)
        description = blank_to_none(form_data["description"])
        plan = form_data["plan"].strip() or "internal"
        status = form_data["status"].strip() or "active"

        if not name:
            errors.append("Workspace name is required.")
        if not slug:
            errors.append("Workspace slug is required.")
        if session.scalar(select(Workspace).where(Workspace.slug == slug)) is not None:
            errors.append("Workspace slug must be unique.")

        if not errors:
            workspace = Workspace(
                name=name,
                slug=slug,
                description=description,
                plan=plan,
                status=status,
            )
            session.add(workspace)
            session.commit()
            upsert_workspace_membership(
                session,
                workspace,
                email=g.current_actor.email,
                display_name=g.current_actor.display_name,
                role="owner",
                commit=True,
            )
            flash("Workspace created successfully.", "success")
            return redirect(url_for("workspaces.detail", slug=workspace.slug))

        flash("Fix the validation issues and try again.", "error")

    return render_template(
        "workspaces/new.html",
        page_title="New Workspace",
        form_data=form_data,
        errors=errors,
    )


@bp.post("/<slug>/members")
def add_member(slug: str):
    session = get_session()
    workspace = get_workspace_for_actor(session, g.current_actor, slug)
    if workspace is None:
        abort(404)

    try:
        require_workspace_role(session, workspace, g.current_actor, roles={"owner", "admin"})
    except PermissionError as exc:
        abort(403, description=str(exc))

    form_data = {
        "email": request.form.get("email", "").strip(),
        "display_name": request.form.get("display_name", "").strip(),
        "role": request.form.get("role", "member").strip() or "member",
    }

    try:
        user, membership, created = upsert_workspace_membership(
            session,
            workspace,
            email=form_data["email"],
            display_name=form_data["display_name"] or None,
            role=form_data["role"],
            commit=True,
        )
    except ValueError as exc:
        memberships = list_workspace_memberships(session, workspace)
        projects = session.scalars(
            select(Project)
            .where(Project.workspace_id == workspace.id)
            .order_by(Project.updated_at.desc(), Project.slug.asc())
        ).all()
        owner_memberships = [item for item in memberships if item.role == "owner"]
        flash("Workspace member update failed. Fix the form and try again.", "error")
        return render_template(
            "workspaces/detail.html",
            page_title=workspace.name,
            workspace=workspace,
            projects=projects,
            memberships=memberships,
            owner_memberships=owner_memberships,
            can_manage_members=True,
            member_form_data=form_data,
            member_errors=[str(exc)],
        )

    flash(
        f"{'Added' if created else 'Updated'} workspace member {user.email} as {membership.role}.",
        "success",
    )
    return redirect(url_for("workspaces.detail", slug=workspace.slug))
