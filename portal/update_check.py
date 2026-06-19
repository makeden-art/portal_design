"""Проверка обновлений портала и модулей (GitHub VERSION / /api/check_update сервиса)."""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any

import httpx

from portal.module_services import MODULE_SERVICES
from portal.modules import MODULE_LABELS, get_enabled_modules
from portal.platform_control import component_runtime_status

VERSION_URLS: dict[str, str] = {
    "portal": "https://raw.githubusercontent.com/makeden-art/portal_design/main/VERSION",
    "convert-to-pdf": "https://raw.githubusercontent.com/makeden-art/Convert-to-PDF/main/VERSION",
    "lisp-calc": "https://raw.githubusercontent.com/makeden-art/lisp_Nikolay/main/VERSION",
    "norm-control": "https://raw.githubusercontent.com/makeden-art/Documentation-compliance-control/main/VERSION",
}

_ENV_URL_KEYS = {
    "portal": "PORTAL_VERSION_URL",
    "convert-to-pdf": "CONVERT_VERSION_URL",
    "lisp-calc": "CALC_VERSION_URL",
    "norm-control": "NORM_VERSION_URL",
}

_MODULE_SERVICE_BASE = {
    "lisp-calc": lambda: os.getenv("CALC_SERVICE_URL", "http://lisp-calc:8000").rstrip("/"),
    "norm-control": lambda: os.getenv("NORM_SERVICE_URL", "http://norm-control:8000").rstrip("/"),
    "convert-to-pdf": lambda: os.getenv("CONVERT_SERVICE_URL", "http://convert-to-pdf:8000").rstrip("/"),
}


def portal_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "1.0.0"


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def _version_url(component_id: str) -> str | None:
    env_key = _ENV_URL_KEYS.get(component_id)
    if env_key:
        override = os.getenv(env_key, "").strip()
        if override:
            return override
    return VERSION_URLS.get(component_id) or None


def fetch_remote_version(component_id: str, timeout: float = 5.0) -> str | None:
    url = _version_url(component_id)
    if not url:
        return None
    try:
        req = urllib.request.Request(url, method="GET")
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            req.add_header("Authorization", f"token {github_token}")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            remote = response.read().decode("utf-8").strip()
        return remote or None
    except Exception:
        return None


def check_portal_update() -> dict[str, Any]:
    current = portal_version()
    remote = fetch_remote_version("portal") or "unknown"
    has_update = bool(remote != "unknown" and parse_version(remote) > parse_version(current))
    return {"current": current, "remote": remote, "has_update": has_update}


async def _fetch_json(url: str, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        return None


async def _module_current_version(component_id: str) -> str | None:
    base = _MODULE_SERVICE_BASE.get(component_id, lambda: "")()
    if not base:
        return None
    for path in ("/version", "/health"):
        data = await _fetch_json(base + path)
        if data and data.get("version"):
            return str(data["version"]).strip()
    return None


async def _check_component_update(module_id: str, component_id: str) -> dict[str, Any] | None:
    rt = component_runtime_status(component_id)
    if not rt.get("installed") or not rt.get("running"):
        return None

    base = _MODULE_SERVICE_BASE.get(component_id, lambda: "")()
    if base:
        api = await _fetch_json(base + "/api/check_update")
        if api and "has_update" in api:
            return {
                "id": module_id,
                "component": component_id,
                "name": MODULE_LABELS.get(module_id, module_id),
                "current": api.get("current"),
                "remote": api.get("remote"),
                "has_update": bool(api.get("has_update")),
            }

    current = await _module_current_version(component_id)
    remote = fetch_remote_version(component_id)
    if not current or not remote:
        return None
    has_update = parse_version(remote) > parse_version(current)
    return {
        "id": module_id,
        "component": component_id,
        "name": MODULE_LABELS.get(module_id, module_id),
        "current": current,
        "remote": remote,
        "has_update": has_update,
    }


async def check_all_updates() -> dict[str, Any]:
    portal = check_portal_update()
    modules: list[dict[str, Any]] = []
    enabled = get_enabled_modules()
    for module_id, component_id in MODULE_SERVICES.items():
        if module_id not in enabled:
            continue
        row = await _check_component_update(module_id, component_id)
        if row:
            modules.append(row)
    has_any = portal["has_update"] or any(m["has_update"] for m in modules)
    return {"portal": portal, "modules": modules, "has_any_update": has_any}
