from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from urllib.parse import urlparse


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def title_from_slug(value: str) -> str:
    parts = [part for part in value.replace("_", "-").split("-") if part]
    if not parts:
        return "Untitled Project"
    return " ".join(part.capitalize() for part in parts)


def normalize_string_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        separators_normalized = value.replace("\r\n", "\n").replace(",", "\n")
        raw_items = separators_normalized.split("\n")
    else:
        raw_items = [value]

    items: list[str] = []
    for item in raw_items:
        cleaned = blank_to_none(str(item))
        if cleaned:
            items.append(cleaned)
    return items


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def decode_text_bytes(raw_bytes: bytes) -> str:
    encodings = [
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1251",
    ]
    attempted: set[str] = set()
    for encoding in encodings:
        if encoding in attempted:
            continue
        attempted.add(encoding)
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def sanitize_relative_path(value: str | None) -> str | None:
    cleaned = blank_to_none(value)
    if not cleaned:
        return None
    if not cleaned.startswith("/"):
        return None
    if cleaned.startswith("//"):
        return None
    return cleaned


def normalize_base_url(value: str | None) -> str | None:
    cleaned = blank_to_none(value)
    if not cleaned:
        return None
    cleaned = cleaned.rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    if parsed.path not in {"", "/"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def is_local_base_url(value: str | None) -> bool:
    normalized = normalize_base_url(value)
    if not normalized:
        return False
    hostname = (urlparse(normalized).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "0.0.0.0"} or hostname.endswith(".local")
