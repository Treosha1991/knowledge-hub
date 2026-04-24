from __future__ import annotations

import os
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    ENV_NAME = os.getenv("KH_ENV", "development").strip().lower()
    ROOT_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = Path(os.getenv("KH_DATA_DIR") or ROOT_DIR / "data" / "knowledge_hub")
    RUNTIME_DIR = Path(os.getenv("KH_RUNTIME_DIR") or DATA_DIR / "runtime")
    LOGS_DIR = Path(os.getenv("KH_LOGS_DIR") or DATA_DIR / "logs")
    BACKUPS_DIR = Path(os.getenv("KH_BACKUPS_DIR") or DATA_DIR / "backups")
    MAIL_OUTBOX_DIR = Path(os.getenv("KH_MAIL_OUTBOX_DIR") or DATA_DIR / "mail_outbox")
    INBOX_DIR = Path(os.getenv("KH_INBOX_DIR") or DATA_DIR / "inbox")
    INBOX_PENDING_DIR = INBOX_DIR / "pending"
    INBOX_PROCESSED_DIR = INBOX_DIR / "processed"
    INBOX_FAILED_DIR = INBOX_DIR / "failed"
    INBOX_WATCHER_STATUS_PATH = RUNTIME_DIR / "inbox_watcher_status.json"
    EXPORTS_DIR = Path(os.getenv("KH_EXPORTS_DIR") or DATA_DIR / "exports")
    PROJECT_EXPORTS_DIR = EXPORTS_DIR / "projects"
    INBOX_WATCHER_TASK_NAME = os.getenv("KH_INBOX_WATCHER_TASK_NAME", "KnowledgeHub Inbox Watcher")
    DAILY_BACKUP_TASK_NAME = os.getenv("KH_DAILY_BACKUP_TASK_NAME", "KnowledgeHub Daily Backup")
    DEFAULT_WORKSPACE_SLUG = os.getenv("KH_DEFAULT_WORKSPACE_SLUG", "personal")
    DEFAULT_WORKSPACE_NAME = os.getenv("KH_DEFAULT_WORKSPACE_NAME", "Personal Workspace")
    DEFAULT_OWNER_EMAIL = os.getenv("KH_DEFAULT_OWNER_EMAIL", "owner@knowledge-hub.local")
    DEFAULT_OWNER_NAME = os.getenv("KH_DEFAULT_OWNER_NAME", "Knowledge Hub Owner")
    DEV_ACTOR_OVERRIDE_ENABLED = _env_flag("KH_DEV_ACTOR_OVERRIDE_ENABLED", True)
    AUTH_REQUIRED = _env_flag("KH_AUTH_REQUIRED", False)
    LOGIN_TOKEN_TTL_MINUTES = int(os.getenv("KH_LOGIN_TOKEN_TTL_MINUTES", "30"))
    MAIL_BACKEND = os.getenv("KH_MAIL_BACKEND", "file")
    MAIL_FROM_ADDRESS = os.getenv("KH_MAIL_FROM_ADDRESS", "noreply@knowledge-hub.local")
    MAIL_FROM_NAME = os.getenv("KH_MAIL_FROM_NAME", "Knowledge Hub")
    PUBLIC_BASE_URL = os.getenv("KH_PUBLIC_BASE_URL", "")
    SMTP_HOST = os.getenv("KH_SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("KH_SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("KH_SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("KH_SMTP_PASSWORD", "")
    SMTP_USE_TLS = _env_flag("KH_SMTP_USE_TLS", True)
    SMTP_USE_SSL = _env_flag("KH_SMTP_USE_SSL", False)
    SMTP_TIMEOUT_SECONDS = int(os.getenv("KH_SMTP_TIMEOUT_SECONDS", "20"))
    DATABASE_URL = os.getenv("KH_DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'knowledge_hub.db').as_posix()}"
    SECRET_KEY = os.getenv("KH_SECRET_KEY", "knowledge-hub-dev-key")
    HOST = os.getenv("KH_HOST", "127.0.0.1")
    PORT = int(os.getenv("KH_PORT", "5001"))
    DEBUG = _env_flag("KH_DEBUG", True)
    TESTING = False
    TRUST_PROXY = _env_flag("KH_TRUST_PROXY", False)
    PREFERRED_URL_SCHEME = "http"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    @classmethod
    def init_app(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        cls.MAIL_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        cls.INBOX_PENDING_DIR.mkdir(parents=True, exist_ok=True)
        cls.INBOX_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        cls.INBOX_FAILED_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROJECT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ProductionConfig(BaseConfig):
    DEBUG = False
    TRUST_PROXY = True
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True


def get_config():
    environment = os.getenv("KH_ENV", "development").strip().lower()
    if environment == "production":
        return ProductionConfig
    return BaseConfig
