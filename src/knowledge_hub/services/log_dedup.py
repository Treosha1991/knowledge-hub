from __future__ import annotations

import re
import unicodedata

from ..models import SessionLog


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def unique_logs_by_meaning(logs: list[SessionLog]) -> list[SessionLog]:
    kept_logs: list[SessionLog] = []
    kept_entries: list[dict] = []

    for log in logs:
        candidate = _build_log_signature(log)
        if any(_is_meaningful_duplicate(candidate, existing) for existing in kept_entries):
            continue
        kept_logs.append(log)
        kept_entries.append(candidate)

    return kept_logs


def _build_log_signature(log: SessionLog) -> dict:
    task = (log.task or "").strip()
    summary = (log.summary or "").strip()
    next_step = (log.next_step or "").strip()
    files_touched = {str(item).strip().lower() for item in (log.files_touched or []) if str(item).strip()}

    return {
        "exact_key": (task, summary, next_step),
        "task_tokens": _token_set(task),
        "summary_tokens": _token_set(summary),
        "next_step_tokens": _token_set(next_step),
        "combined_tokens": _token_set(" ".join(part for part in (task, summary, next_step) if part)),
        "files_touched": files_touched,
    }


def _is_meaningful_duplicate(candidate: dict, existing: dict) -> bool:
    if candidate["exact_key"] == existing["exact_key"]:
        return True

    combined_similarity = _jaccard(candidate["combined_tokens"], existing["combined_tokens"])
    next_step_similarity = _jaccard(candidate["next_step_tokens"], existing["next_step_tokens"])
    file_overlap = bool(candidate["files_touched"] and existing["files_touched"] and candidate["files_touched"] & existing["files_touched"])

    if file_overlap and combined_similarity >= 0.42:
        return True

    if next_step_similarity >= 0.7 and combined_similarity >= 0.35:
        return True

    task_similarity = _jaccard(candidate["task_tokens"], existing["task_tokens"])
    summary_similarity = _jaccard(candidate["summary_tokens"], existing["summary_tokens"])
    if task_similarity >= 0.7 and summary_similarity >= 0.35:
        return True

    return False


def _token_set(value: str) -> set[str]:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    parts = re.split(r"[^a-z0-9]+", ascii_text)
    return {
        part
        for part in parts
        if len(part) >= 3 and part not in _STOP_WORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
