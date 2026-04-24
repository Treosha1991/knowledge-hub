from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _status_path(config) -> Path:
    return Path(config["INBOX_WATCHER_STATUS_PATH"])


def write_inbox_watcher_status(config, payload: dict[str, Any]) -> dict[str, Any]:
    path = _status_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = {
        **payload,
        "updated_at": _utc_now_iso(),
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return enriched


def mark_inbox_watcher_started(config, *, pid: int, interval_seconds: float) -> dict[str, Any]:
    return write_inbox_watcher_status(
        config,
        {
            "exists": True,
            "state": "running",
            "mode": "watch",
            "pid": pid,
            "interval_seconds": interval_seconds,
            "started_at": _utc_now_iso(),
            "last_heartbeat_at": None,
            "last_cycle_at": None,
            "last_summary": None,
            "last_error": None,
        },
    )


def mark_inbox_watcher_heartbeat(
    config,
    *,
    summary: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    current = get_inbox_watcher_status(config, compute_runtime_state=False)
    state = "running" if error is None else "error"
    return write_inbox_watcher_status(
        config,
        {
            **current,
            "exists": True,
            "state": state,
            "last_heartbeat_at": _utc_now_iso(),
            "last_cycle_at": _utc_now_iso(),
            "last_summary": summary,
            "last_error": error,
        },
    )


def mark_inbox_watcher_stopped(config, *, reason: str = "stopped") -> dict[str, Any]:
    current = get_inbox_watcher_status(config, compute_runtime_state=False)
    return write_inbox_watcher_status(
        config,
        {
            **current,
            "exists": True,
            "state": "stopped",
            "stopped_at": _utc_now_iso(),
            "stop_reason": reason,
        },
    )


def get_inbox_watcher_status(config, *, compute_runtime_state: bool = True) -> dict[str, Any]:
    path = _status_path(config)
    default = {
        "exists": False,
        "state": "not_started",
        "mode": None,
        "pid": None,
        "interval_seconds": None,
        "started_at": None,
        "stopped_at": None,
        "stop_reason": None,
        "last_heartbeat_at": None,
        "last_cycle_at": None,
        "last_summary": None,
        "last_error": None,
        "status_path": str(path),
        "heartbeat_age_seconds": None,
        "stale_after_seconds": None,
        "is_running": False,
    }

    if not path.exists():
        return default

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **default,
            "exists": True,
            "state": "error",
            "last_error": str(exc),
        }

    status = {
        **default,
        **payload,
        "exists": True,
        "status_path": str(path),
    }
    if not compute_runtime_state:
        return status

    interval_seconds = float(status["interval_seconds"] or 5.0)
    stale_after_seconds = max(int(interval_seconds * 3), 15)
    last_heartbeat = _parse_iso_datetime(status.get("last_heartbeat_at"))
    heartbeat_age_seconds: int | None = None

    if last_heartbeat is not None:
        heartbeat_age_seconds = max(int((_utc_now() - last_heartbeat).total_seconds()), 0)

    runtime_state = status["state"]
    is_running = runtime_state == "running"
    if runtime_state in {"running", "error"} and last_heartbeat is not None:
        if _utc_now() > last_heartbeat + timedelta(seconds=stale_after_seconds):
            runtime_state = "stale"
            is_running = False
    elif runtime_state == "running" and last_heartbeat is None:
        is_running = False

    return {
        **status,
        "state": runtime_state,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "is_running": is_running,
    }
