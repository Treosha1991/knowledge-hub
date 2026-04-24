from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, Workspace, WorkspaceMembership
from ..utils import blank_to_none


DEFAULT_OWNER_EMAIL = "owner@knowledge-hub.local"
DEFAULT_OWNER_NAME = "Knowledge Hub Owner"
MEMBERSHIP_ROLES = {"owner", "admin", "member"}


def ensure_default_owner(db_session: Session, config=None, *, commit: bool = True) -> User:
    email = (
        blank_to_none(_config_value(config, "DEFAULT_OWNER_EMAIL", DEFAULT_OWNER_EMAIL))
        or DEFAULT_OWNER_EMAIL
    ).strip().lower()
    display_name = (
        blank_to_none(_config_value(config, "DEFAULT_OWNER_NAME", DEFAULT_OWNER_NAME))
        or DEFAULT_OWNER_NAME
    ).strip()

    user = db_session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            status="active",
        )
        db_session.add(user)
        if commit:
            db_session.commit()
            db_session.refresh(user)
        else:
            db_session.flush()
        return user

    user_changed = False
    if not user.display_name and display_name:
        user.display_name = display_name
        user_changed = True
    if not user.status:
        user.status = "active"
        user_changed = True

    if user_changed:
        if commit:
            db_session.commit()
            db_session.refresh(user)
        else:
            db_session.flush()

    return user


def ensure_user(
    db_session: Session,
    *,
    email: str,
    display_name: str | None = None,
    status: str = "active",
    commit: bool = True,
) -> tuple[User, bool]:
    normalized_email = (blank_to_none(email) or "").strip().lower()
    if not normalized_email:
        raise ValueError("User email is required.")

    normalized_name = blank_to_none(display_name) or normalized_email.split("@")[0].replace(".", " ").title()
    user = db_session.scalar(select(User).where(User.email == normalized_email))
    created = False

    if user is None:
        user = User(
            email=normalized_email,
            display_name=normalized_name,
            status=status or "active",
        )
        db_session.add(user)
        created = True
    else:
        if normalized_name and normalized_name != user.display_name:
            user.display_name = normalized_name
        if status and status != user.status:
            user.status = status

    if commit:
        db_session.commit()
        db_session.refresh(user)
    else:
        db_session.flush()

    return user, created


def ensure_workspace_owner(
    db_session: Session,
    workspace: Workspace,
    *,
    owner_user: User | None = None,
    config=None,
    commit: bool = True,
) -> WorkspaceMembership:
    owner = owner_user or ensure_default_owner(db_session, config, commit=False)
    membership = db_session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == owner.id,
        )
    )

    if membership is None:
        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=owner.id,
            role="owner",
            status="active",
        )
        db_session.add(membership)
    else:
        if membership.role != "owner":
            membership.role = "owner"
        if membership.status != "active":
            membership.status = "active"

    if commit:
        db_session.commit()
        db_session.refresh(membership)
    else:
        db_session.flush()

    return membership


def ensure_workspaces_have_owner(db_session: Session, config=None, *, commit: bool = True) -> list[WorkspaceMembership]:
    owner = ensure_default_owner(db_session, config, commit=False)
    owner_memberships: list[WorkspaceMembership] = []

    workspaces = db_session.scalars(select(Workspace).order_by(Workspace.id.asc())).all()
    for workspace in workspaces:
        owner_membership = db_session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace.id,
                WorkspaceMembership.role == "owner",
            )
        )
        if owner_membership is None:
            owner_membership = ensure_workspace_owner(
                db_session,
                workspace,
                owner_user=owner,
                config=config,
                commit=False,
            )
        owner_memberships.append(owner_membership)

    if commit:
        db_session.commit()

    return owner_memberships


def list_workspace_memberships(db_session: Session, workspace: Workspace) -> list[WorkspaceMembership]:
    memberships = db_session.scalars(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace.id)
        .join(WorkspaceMembership.user)
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()

    return sorted(
        memberships,
        key=lambda item: (
            0 if item.role == "owner" else 1,
            (item.user.display_name or "").lower(),
            item.user.email.lower(),
        ),
    )


def get_workspace_membership(
    db_session: Session,
    workspace: Workspace,
    user: User,
) -> WorkspaceMembership | None:
    return db_session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
    )


def user_is_workspace_owner(
    db_session: Session,
    workspace: Workspace,
    user: User,
) -> bool:
    membership = get_workspace_membership(db_session, workspace, user)
    return membership is not None and membership.status == "active" and membership.role == "owner"


def upsert_workspace_membership(
    db_session: Session,
    workspace: Workspace,
    *,
    email: str,
    display_name: str | None = None,
    role: str = "member",
    status: str = "active",
    commit: bool = True,
) -> tuple[User, WorkspaceMembership, bool]:
    normalized_role = (blank_to_none(role) or "member").strip().lower()
    if normalized_role not in MEMBERSHIP_ROLES:
        raise ValueError(f"Membership role must be one of: {', '.join(sorted(MEMBERSHIP_ROLES))}.")

    user, _created_user = ensure_user(
        db_session,
        email=email,
        display_name=display_name,
        status="active",
        commit=False,
    )
    membership = get_workspace_membership(db_session, workspace, user)
    created = False

    if membership is None:
        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=normalized_role,
            status=status or "active",
        )
        db_session.add(membership)
        created = True
    else:
        membership.role = normalized_role
        membership.status = status or "active"

    if commit:
        db_session.commit()
        db_session.refresh(user)
        db_session.refresh(membership)
    else:
        db_session.flush()

    return user, membership, created


def _config_value(config, key: str, fallback):
    if config is None:
        return fallback
    return config.get(key, fallback)
