from __future__ import annotations

from urllib.parse import urljoin

from flask import url_for

from ..utils import normalize_base_url


def get_public_base_url(config) -> str | None:
    return normalize_base_url(config.get("PUBLIC_BASE_URL"))


def build_external_url(endpoint: str, config, **values) -> str:
    base_url = get_public_base_url(config)
    if not base_url:
        return url_for(endpoint, _external=True, **values)

    relative_path = url_for(endpoint, _external=False, **values)
    return urljoin(base_url + "/", relative_path.lstrip("/"))
