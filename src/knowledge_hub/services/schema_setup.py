from __future__ import annotations

from sqlalchemy import inspect, text

from ..db import create_all, get_engine, get_session, remove_session
from ..models import Project
from .ownership import ensure_workspaces_have_owner
from .workspaces import ensure_default_workspace


def ensure_application_schema(app) -> None:
    create_all(app)
    engine = get_engine(app)

    with engine.begin() as connection:
        inspector = inspect(connection)
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "workspace_id" not in project_columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN workspace_id INTEGER")
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_projects_workspace_id ON projects (workspace_id)"
        )

    session = get_session()
    try:
        default_workspace = ensure_default_workspace(session, app.config, commit=False)
        session.execute(
            text(
                "UPDATE projects SET workspace_id = :workspace_id "
                "WHERE workspace_id IS NULL"
            ),
            {"workspace_id": default_workspace.id},
        )
        ensure_workspaces_have_owner(session, app.config, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        remove_session()
