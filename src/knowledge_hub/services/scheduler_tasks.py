from __future__ import annotations

import shutil
import subprocess
from typing import Any


def get_scheduler_task_status(task_name: str) -> dict[str, Any]:
    if not shutil.which("schtasks.exe"):
        return {
            "task_name": task_name,
            "available": False,
            "registered": False,
            "error": "schtasks.exe is not available on this system.",
        }

    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return {
            "task_name": task_name,
            "available": False,
            "registered": False,
            "error": str(exc),
        }

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return {
            "task_name": task_name,
            "available": True,
            "registered": False,
            "error": output or "Task was not found.",
        }

    fields = _parse_list_output(output)
    return {
        "task_name": task_name,
        "available": True,
        "registered": True,
        "status": _pick_field(fields, ["Status", "Scheduled Task State"]),
        "next_run_time": _pick_field(fields, ["Next Run Time"]),
        "last_run_time": _pick_field(fields, ["Last Run Time"]),
        "last_result": _pick_field(fields, ["Last Result"]),
        "schedule": _pick_field(fields, ["Schedule", "Schedule Type"]),
        "task_to_run": _pick_field(fields, ["Task To Run"]),
        "author": _pick_field(fields, ["Author"]),
        "raw_fields": fields,
    }


def list_knowledge_hub_scheduler_tasks(config) -> list[dict[str, Any]]:
    return [
        {
            "kind": "inbox_watcher",
            "display_name": "Inbox Watcher Task",
            **get_scheduler_task_status(str(config["INBOX_WATCHER_TASK_NAME"])),
        },
        {
            "kind": "daily_backup",
            "display_name": "Daily Backup Task",
            **get_scheduler_task_status(str(config["DAILY_BACKUP_TASK_NAME"])),
        },
    ]


def _parse_list_output(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _pick_field(fields: dict[str, str], names: list[str]) -> str | None:
    for name in names:
        if name in fields:
            return fields[name]
    return None
