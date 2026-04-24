from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class CreatedAtMixin:
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="internal")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    login_tokens: Mapped[list["LoginToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class WorkspaceMembership(Base, TimestampMixin):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    workspace: Mapped["Workspace"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stack: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    current_goal: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[str | None] = mapped_column(Text)

    workspace: Mapped["Workspace | None"] = relationship(back_populates="projects")
    session_logs: Mapped[list["SessionLog"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    prompt_templates: Mapped[list["PromptTemplate"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    automation_events: Mapped[list["AutomationEvent"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class SessionLog(Base, CreatedAtMixin):
    __tablename__ = "session_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    task: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    actions_taken: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    files_touched: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_step: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_json: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="session_logs")


class PromptTemplate(Base, TimestampMixin):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="prompt_templates")


class Snapshot(Base, TimestampMixin):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="snapshots")


class AutomationEvent(Base, CreatedAtMixin):
    __tablename__ = "automation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project | None"] = relationship(back_populates="automation_events")


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="api_tokens")


class LoginToken(Base, CreatedAtMixin):
    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="login")
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="login_tokens")
