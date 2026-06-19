"""Управление контейнерами платформы через Docker Compose на хосте."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from portal import modules as portal_modules
from portal.modules import get_all_modules, get_enabled_modules
from portal.platform_services import component_runtime_defs

PLATFORM_ROOT = Path(os.getenv("PLATFORM_INSTALL_ROOT", "/opt/road-pdf-platform"))
COMPOSE_FILE = Path(
    os.getenv("PLATFORM_COMPOSE_FILE", str(PLATFORM_ROOT / "docker-compose.platform.yml"))
)
RUNTIME_ENV = PLATFORM_ROOT / "platform.runtime.env"
STATE_FILE = PLATFORM_ROOT / "platform.state.json"
COMPOSE_BIN = os.getenv("DOCKER_COMPOSE_BIN", "docker-compose")


def _module_service_map() -> dict[str, str]:
    try:
        from portal.module_services import MODULE_SERVICES

        return dict(MODULE_SERVICES)
    except Exception:
        return {"calc": "lisp-calc", "norm": "norm-control"}


def _component_defs() -> dict[str, dict[str, Any]]:
    return component_runtime_defs(
        root=PLATFORM_ROOT,
        masha_container=os.getenv("MASHA_CONTAINER"),
    )


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"disabled_services": [], "portal_modules": list(get_all_modules())}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    _sync_runtime_env(state)


def _sync_runtime_env(state: dict[str, Any]) -> None:
    modules = state.get("portal_modules") or list(get_all_modules())
    lines = [f"PORTAL_MODULES={','.join(modules)}"]
    RUNTIME_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _compose(*args: str, timeout: int = 180) -> dict[str, Any]:
    if not COMPOSE_FILE.exists():
        return {"ok": False, "error": f"Compose-файл не найден: {COMPOSE_FILE}"}
    cmd = [COMPOSE_BIN, "-f", str(COMPOSE_FILE)]
    state = _load_state()
    disabled = set(state.get("disabled_services") or [])
    profiles: set[str] = set()
    for cid, meta in _component_defs().items():
        if meta.get("profile") and cid not in disabled:
            profiles.add(meta["profile"])
    for p in sorted(profiles):
        cmd.extend(["--profile", p])
    if RUNTIME_ENV.exists():
        cmd.extend(["--env-file", str(RUNTIME_ENV)])
    cmd.extend(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PLATFORM_ROOT),
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": (proc.stderr or proc.stdout or "compose error").strip(),
                "command": " ".join(cmd),
            }
        return {"ok": True, "message": (proc.stdout or "OK").strip(), "command": " ".join(cmd)}
    except FileNotFoundError:
        return {"ok": False, "error": f"Не найден {COMPOSE_BIN}. Пересоберите образ портала."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Таймаут выполнения docker compose"}


def compose_update_service(service: str) -> dict[str, Any]:
    """Обновить сервис через docker compose pull + up (fallback без Watchtower)."""
    pull = _compose("pull", service, timeout=300)
    if not pull.get("ok"):
        return {**pull, "via": "compose"}
    up = _compose("up", "-d", service, "--no-build", "--force-recreate", timeout=180)
    up["via"] = "compose"
    return up


def compose_service_for_image(image: str) -> str | None:
    portal_image = os.getenv("PORTAL_IMAGE", "makeden/portal:latest")
    mapping = {
        portal_image: "portal",
        "makeden/portal:latest": "portal",
        "makeden/lisp_calc:latest": "lisp-calc",
        "makeden/norm_control:latest": "norm-control",
        "makeden/convert-to-pdf:latest": "convert-to-pdf",
        os.getenv("MASHA_IMAGE", "makeden/masha-print:latest"): "masha-print",
    }
    return mapping.get(image)


def _container_names(name: str) -> list[str]:
    aliases = {
        "masha-print-service": ["masha-print"],
        "masha-print": ["masha-print-service"],
    }
    return [name, *aliases.get(name, [])]


def _docker_ps_names(filter_arg: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--filter", filter_arg, "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return []
        return [n.strip() for n in proc.stdout.splitlines() if n.strip()]
    except Exception:
        return []


def resolve_container(name: str, compose_service: str | None = None) -> str | None:
    """Имя контейнера: точное, по compose-метке или по подстроке (orphan-префикс)."""
    if not name:
        return None
    for candidate in _container_names(name):
        try:
            proc = subprocess.run(
                ["docker", "inspect", candidate],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return candidate
        except Exception:
            continue
    if compose_service:
        by_label = _docker_ps_names(f"label=com.docker.compose.service={compose_service}")
        if by_label:
            return by_label[0]
    by_name = _docker_ps_names(f"name={name}")
    if by_name:
        for candidate in by_name:
            if candidate == name or candidate.endswith(f"_{name}"):
                return candidate
        return by_name[0]
    return None


def container_running(name: str, compose_service: str | None = None) -> bool:
    resolved = resolve_container(name, compose_service)
    if not resolved:
        return False
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", resolved],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:
        return False


def container_image_version(container_name: str, compose_service: str | None = None) -> str | None:
    """Версия из OCI-метки образа (fallback, если /version в контейнере старый)."""
    resolved = resolve_container(container_name, compose_service)
    if not resolved:
        return None
    try:
        proc = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                '{{index .Config.Labels "org.opencontainers.image.version"}}',
                resolved,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            ver = proc.stdout.strip()
            if ver and ver != "<no value>":
                return ver
    except Exception:
        pass
    return None


def container_exists(name: str, compose_service: str | None = None) -> bool:
    return resolve_container(name, compose_service) is not None


def install_component(component_id: str) -> dict[str, Any]:
    meta = _component_defs().get(component_id)
    if not meta:
        return {"ok": False, "error": "Неизвестный компонент"}
    if meta.get("no_uninstall") and component_id == "portal":
        return {"ok": False, "error": "Портал нельзя установить отдельно — он уже ядро системы"}
    state = _load_state()
    disabled = set(state.get("disabled_services") or [])
    disabled.discard(component_id)
    state["disabled_services"] = sorted(disabled)
    _save_state(state)
    result = _compose("up", "-d", meta["service"])
    result["component_id"] = component_id
    result["action"] = "install"
    return result


def uninstall_component(component_id: str) -> dict[str, Any]:
    meta = _component_defs().get(component_id)
    if not meta:
        return {"ok": False, "error": "Неизвестный компонент"}
    if meta.get("no_uninstall"):
        return {"ok": False, "error": "Этот компонент нельзя удалить — он обязателен для платформы"}
    state = _load_state()
    disabled = set(state.get("disabled_services") or [])
    disabled.add(component_id)
    state["disabled_services"] = sorted(disabled)
    _save_state(state)
    stop = _compose("stop", meta["service"])
    if not stop.get("ok"):
        return stop
    rm = _compose("rm", "-f", meta["service"])
    rm["component_id"] = component_id
    rm["action"] = "uninstall"
    return rm


def set_portal_module(module_id: str, enabled: bool) -> dict[str, Any]:
    known = get_all_modules()
    if module_id not in known:
        return {"ok": False, "error": "Неизвестный модуль портала"}
    state = _load_state()
    modules = set(state.get("portal_modules") or list(known))
    if enabled:
        modules.add(module_id)
    else:
        modules.discard(module_id)
    state["portal_modules"] = [m for m in known if m in modules]
    _save_state(state)

    svc_map = _module_service_map()
    compose_result: dict[str, Any] = {"ok": True}
    service = svc_map.get(module_id)
    if service:
        if enabled:
            compose_result = _compose("up", "-d", service)
        else:
            compose_result = _compose("stop", service)

    ok = compose_result.get("ok", True)
    return {
        "ok": ok,
        "message": compose_result.get("message")
        or ("Модуль включён, контейнер запускается." if enabled else "Модуль отключён, контейнер остановлен."),
        "error": compose_result.get("error"),
        "module_id": module_id,
        "enabled": enabled,
        "portal_modules": state["portal_modules"],
        "action": "portal_module_toggle",
    }


def component_runtime_status(component_id: str) -> dict[str, Any]:
    meta = _component_defs().get(component_id, {})
    state = _load_state()
    disabled = set(state.get("disabled_services") or [])
    container = meta.get("container", "")
    service = meta.get("service")
    running = container_running(container, service)
    if component_id in disabled:
        installed = False
    elif component_id in ("portal", "watchtower"):
        installed = True
    else:
        installed = container_exists(container, service)
    return {
        "id": component_id,
        "installed": installed,
        "running": running,
        "disabled_in_state": component_id in disabled,
    }
