from __future__ import annotations

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


SessionLocal = scoped_session(
    sessionmaker(
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
)


def init_db(app: Flask) -> Engine:
    database_url = app.config["DATABASE_URL"]
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    SessionLocal.configure(bind=engine)
    app.extensions["knowledge_hub_engine"] = engine

    @app.teardown_appcontext
    def remove_session(_exception=None) -> None:
        SessionLocal.remove()

    return engine


def get_engine(app: Flask) -> Engine:
    return app.extensions["knowledge_hub_engine"]


def get_session():
    return SessionLocal()


def remove_session() -> None:
    SessionLocal.remove()


def create_all(app: Flask) -> None:
    Base.metadata.create_all(bind=get_engine(app))
