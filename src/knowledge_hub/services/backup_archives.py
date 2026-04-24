from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import zipfile


@dataclass
class BackupArchiveInfo:
    filename: str
    path: str
    created_at: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "path": self.path,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
        }


@dataclass
class BackupCreateResult:
    archive: BackupArchiveInfo
    included_items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive": self.archive.to_dict(),
            "included_items": self.included_items,
        }


def create_backup_archive(config) -> BackupCreateResult:
    backups_dir = Path(config["BACKUPS_DIR"])
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    archive_path = _next_backup_path(backups_dir, timestamp)

    included_items: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        sqlite_path = get_sqlite_database_path(config)
        if sqlite_path and sqlite_path.exists():
            _write_file_to_archive(archive, sqlite_path, Path("database") / sqlite_path.name)
            included_items.append(
                {
                    "kind": "database",
                    "source_path": str(sqlite_path),
                    "archive_path": f"database/{sqlite_path.name}",
                }
            )

        exports_dir = Path(config["EXPORTS_DIR"])
        if exports_dir.exists():
            count = _write_directory_to_archive(archive, exports_dir, Path("exports"))
            included_items.append(
                {
                    "kind": "exports",
                    "source_path": str(exports_dir),
                    "archive_path": "exports/",
                    "file_count": count,
                }
            )

        runtime_dir = Path(config["RUNTIME_DIR"])
        if runtime_dir.exists():
            count = _write_directory_to_archive(archive, runtime_dir, Path("runtime"))
            included_items.append(
                {
                    "kind": "runtime",
                    "source_path": str(runtime_dir),
                    "archive_path": "runtime/",
                    "file_count": count,
                }
            )

        manifest = {
            "created_at": _utc_now_iso(),
            "included_items": included_items,
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return BackupCreateResult(
        archive=BackupArchiveInfo(
            filename=archive_path.name,
            path=str(archive_path),
            created_at=_path_timestamp(archive_path),
            size_bytes=archive_path.stat().st_size,
        ),
        included_items=included_items,
    )


def list_recent_backups(config, *, limit: int = 5) -> list[dict[str, Any]]:
    backups_dir = Path(config["BACKUPS_DIR"])
    if not backups_dir.exists():
        return []

    items = sorted(backups_dir.glob("knowledge_hub_backup_*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_backup_info(path).to_dict() for path in items[: max(limit, 0)]]


def get_latest_backup(config) -> dict[str, Any] | None:
    items = list_recent_backups(config, limit=1)
    return items[0] if items else None


def get_sqlite_database_path(config) -> Path | None:
    database_url = str(config["DATABASE_URL"])
    if not database_url.startswith("sqlite:///"):
        return None

    parsed = urlparse(database_url)
    raw_path = parsed.path or database_url.removeprefix("sqlite:///")
    decoded = unquote(raw_path)
    if decoded.startswith("/") and len(decoded) > 2 and decoded[2] == ":":
        decoded = decoded[1:]
    return Path(decoded)


def _write_directory_to_archive(archive: zipfile.ZipFile, source_dir: Path, archive_root: Path) -> int:
    count = 0
    for path in sorted(source_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source_dir)
            _write_file_to_archive(archive, path, archive_root / relative)
            count += 1
    return count


def _write_file_to_archive(archive: zipfile.ZipFile, source_path: Path, archive_path: Path) -> None:
    archive.write(source_path, arcname=archive_path.as_posix())


def _backup_info(path: Path) -> BackupArchiveInfo:
    return BackupArchiveInfo(
        filename=path.name,
        path=str(path),
        created_at=_path_timestamp(path),
        size_bytes=path.stat().st_size,
    )


def _path_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _next_backup_path(backups_dir: Path, timestamp: str) -> Path:
    candidate = backups_dir / f"knowledge_hub_backup_{timestamp}.zip"
    counter = 1
    while candidate.exists():
        candidate = backups_dir / f"knowledge_hub_backup_{timestamp}_{counter:02d}.zip"
        counter += 1
    return candidate


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()
