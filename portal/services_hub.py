"""
Портал управления: статусы сервисов, версии, обновления через Watchtower.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse, JSONResponse

from portal.platform_control import (
    COMPOSE_FILE,
    _component_defs,
    component_runtime_status,
    install_component,
    set_portal_module,
    uninstall_component,
)
from portal.modules import (
    modules_config_hint,
    modules_status,
    portal_features_list,
    registered_plugins,
    utility_links as portal_utility_links,
)

router = APIRouter()

WATCHTOWER_URL = os.getenv("WATCHTOWER_URL", "http://watchtower:8080/v1/update")
WATCHTOWER_TOKEN = os.getenv("WATCHTOWER_TOKEN", "platform_watchtower_secret")
PLATFORM_ROOT = os.getenv("PLATFORM_INSTALL_ROOT", "/opt/road-pdf-platform")


def _compose_shell_hint() -> str:
    compose_name = os.getenv(
        "PLATFORM_COMPOSE_FILE",
        str(COMPOSE_FILE),
    )
    return f"cd {PLATFORM_ROOT} && docker compose -f {Path(compose_name).name}"


def _platform_catalog() -> list[dict[str, Any]]:
    """Полный каталог компонентов платформы (что можно установить)."""
    compose = _compose_shell_hint()
    return [
        {
            "id": "portal",
            "role": "core",
            "icon": "🏗️",
            "name": "Портал управления",
            "tagline": "Ядро платформы — всегда установлено",
            "description": (
                "Хаб утилит, страница сервисов, Watchtower. "
                "Репозиторий portal_design. Утилиты подключаются модулями."
            ),
            "features_dynamic": True,
            "publishable": True,
            "required": True,
            "compose_service": "portal",
            "install_hint": None,
        },
        {
            "id": "lisp-calc",
            "role": "module",
            "icon": "🏗️",
            "name": "Поперечники (lisp_Nikolay)",
            "tagline": "Отдельный контейнер",
            "description": "Калькулятор поперечников DXF/DWG. Репозиторий makeden-art/lisp_Nikolay.",
            "features": ["Расчёт объёмов", "Экспорт CSV/DXF", "Маршрут портала /calc"],
            "publishable": True,
            "required": False,
            "compose_service": "lisp-calc",
            "public_url": os.getenv("CALC_PUBLIC_URL", "http://192.168.88.10:8082/"),
            "install_hint": f"{compose} up -d lisp-calc",
        },
        {
            "id": "convert-to-pdf",
            "role": "module",
            "icon": "📄",
            "name": "Перевод в PDF",
            "tagline": "Отдельный контейнер",
            "description": "Перевод редактируемых документов в PDF. Репозиторий makeden-art/Convert-to-PDF.",
            "features": ["DOC/DOCX/XLS/XLSX → PDF", "DWG/DXF → PDF (ODA)", "Маршрут портала /convert"],
            "publishable": True,
            "required": False,
            "compose_service": "convert-to-pdf",
            "public_url": os.getenv("CONVERT_PUBLIC_URL", "http://192.168.88.10:8084/"),
            "install_hint": f"{compose} up -d convert-to-pdf",
        },
        {
            "id": "norm-control",
            "role": "module",
            "icon": "📏",
            "name": "Нормоконтроль (doc-compliance)",
            "tagline": "Отдельный контейнер",
            "description": "Пакетный нормоконтроль. Репозиторий Documentation-compliance-control.",
            "features": ["Проверка DWG/DXF/PDF/DOCX", "Маршрут портала /norm"],
            "publishable": True,
            "required": False,
            "compose_service": "norm-control",
            "public_url": os.getenv("NORM_PUBLIC_URL", "http://192.168.88.10:8083/"),
            "install_hint": f"{compose} up -d norm-control",
        },
        {
            "id": "masha-print",
            "role": "addon",
            "icon": "🖨️",
            "name": "Маша — печать и анализ PDF",
            "tagline": "Дополнительный модуль платформы",
            "description": (
                "Сервис печати: анализ PDF, очередь, принтеры. "
                "Собственное обновление по VERSION (репозиторий masha-print)."
            ),
            "features": [
                "Загрузка и анализ PDF",
                "Очередь печати и принтеры CUPS",
                "Интеграция с порталом (PDF-конвейер)",
            ],
            "publishable": True,
            "required": False,
            "compose_service": "masha-print",
            "install_hint": f"{compose} up -d masha-print",
        },
        {
            "id": "watchtower",
            "role": "infra",
            "icon": "🔄",
            "name": "Watchtower",
            "tagline": "Слежение за обновлениями Docker-образов",
            "description": (
                "Фоновый сервис: раз в час проверяет registry и по кнопке "
                "«Обновить» перезапускает контейнеры с новым образом."
            ),
            "features": [
                "Авто-проверка Docker Hub",
                "Обновление по кнопке из портала",
                "Отдельный scope для портала и masha-print",
            ],
            "publishable": True,
            "required": True,
            "compose_service": "watchtower",
            "install_hint": f"{compose} up -d watchtower",
        },
    ]


def _default_services() -> list[dict[str, Any]]:
    return [
        {
            "id": "portal",
            "name": "Портал (geo_calc_app)",
            "description": "Хаб утилит, PDF-конвейер, поперечники, нормоконтроль",
            "container": "geo_calc_app",
            "image": os.getenv("PORTAL_IMAGE", "makeden/portal:latest"),
            "health_url": "http://127.0.0.1:8000/version",
            "public_url": "/",
            "utility_links_dynamic": True,
            "watchtower": True,
            "watchtower_scope": "portal",
            "version_source": "portal",
        },
        {
            "id": "masha-print",
            "name": "Печать / PDF (masha-print)",
            "description": "Анализ PDF, очередь печати",
            "container": os.getenv("MASHA_CONTAINER", "masha-print-service"),
            "image": os.getenv("MASHA_IMAGE", "makeden/masha-print:latest"),
            "health_url": os.getenv(
                "MASHA_PRINT_URL", "http://masha-print:8000"
            ).rstrip("/")
            + "/api/license/status",
            "public_url": os.getenv("MASHA_PUBLIC_URL", "http://192.168.88.10:8000/"),
            "utility_links": [],
            "watchtower": True,
            "watchtower_scope": "masha",
            "version_source": "masha",
        },
        {
            "id": "watchtower",
            "name": "Watchtower",
            "description": "Автообновление образов контейнеров",
            "container": "watchtower",
            "image": "containrrr/watchtower:latest",
            "health_url": None,
            "public_url": None,
            "utility_links": [],
            "watchtower": False,
            "version_source": "static",
            "version": "latest",
        },
    ]


def get_services_config() -> list[dict[str, Any]]:
    raw = os.getenv("SERVICES_HUB_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    services = _default_services()
    for svc in services:
        if svc.get("utility_links_dynamic"):
            svc["utility_links"] = portal_utility_links()
            del svc["utility_links_dynamic"]
        if svc.get("features_dynamic"):
            svc["features"] = portal_features_list()
            del svc["features_dynamic"]
    local = os.getenv("LOCAL_SERVICES_JSON", "").strip()
    if local:
        try:
            services.extend(json.loads(local))
        except json.JSONDecodeError:
            pass
    return services


def _portal_version() -> str:
    from pathlib import Path

    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "0.0.0"


async def _fetch_health(url: str | None, timeout: float = 5.0) -> dict[str, Any]:
    if not url:
        return {"reachable": None, "detail": "no health endpoint"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            body = None
            try:
                body = r.json()
            except Exception:
                body = r.text[:200]
            return {
                "reachable": True,
                "http_status": r.status_code,
                "healthy": 200 <= r.status_code < 300,
                "body": body,
            }
    except Exception as e:
        return {"reachable": False, "healthy": False, "detail": str(e)}


async def _service_version(svc: dict[str, Any]) -> str:
    src = svc.get("version_source", "")
    if src == "portal":
        return _portal_version()
    if src == "static":
        return svc.get("version", "—")
    if src == "masha":
        base = os.getenv("MASHA_PRINT_URL", "http://masha-print:8000").rstrip("/")
        h = await _fetch_health(base + "/version")
        if h.get("body") and isinstance(h["body"], dict):
            ver = h["body"].get("version")
            if ver:
                return str(ver)
        return "up" if h.get("healthy") else "down"
    return "—"


def _module_service_base(component_id: str) -> str | None:
    """Внутренний URL модуля в docker-сети платформы."""
    mapping = {
        "lisp-calc": os.getenv("CALC_SERVICE_URL", "http://lisp-calc:8000"),
        "norm-control": os.getenv("NORM_SERVICE_URL", "http://norm-control:8000"),
        "convert-to-pdf": os.getenv("CONVERT_SERVICE_URL", "http://convert-to-pdf:8000"),
    }
    base = mapping.get(component_id)
    return base.rstrip("/") if base else None


async def _fetch_module_version(component_id: str) -> str:
    base = _module_service_base(component_id)
    if not base:
        return "—"
    for path in ("/version", "/health"):
        h = await _fetch_health(base + path)
        body = h.get("body")
        if isinstance(body, dict):
            ver = body.get("version")
            if ver:
                return str(ver).strip()
        if h.get("healthy"):
            return "up"
    return "—"


def _status_from_health(health: dict[str, Any]) -> str:
    if health.get("healthy"):
        return "online"
    if health.get("reachable") is False:
        return "offline"
    return "degraded"


async def build_services_status() -> list[dict[str, Any]]:
    out = []
    for svc in get_services_config():
        health = await _fetch_health(svc.get("health_url"))
        version = await _service_version(svc)
        if not svc.get("health_url"):
            status = "online"
        else:
            status = _status_from_health(health)
        out.append(
            {
                **svc,
                "version": version,
                "health": health,
                "status": status,
            }
        )
    return out


async def build_platform_components() -> list[dict[str, Any]]:
    """Каталог + живой статус: что установлено, что доступно для установки."""
    services_by_id = {s["id"]: s for s in await build_services_status()}
    out: list[dict[str, Any]] = []
    for item in _platform_catalog():
        svc = services_by_id.get(item["id"])
        if svc:
            status = svc["status"]
            version = svc.get("version", "—")
            installed = status == "online" or item.get("required")
            watchtower = svc.get("watchtower", False)
            image = svc.get("image")
            container = svc.get("container")
            public_url = svc.get("public_url")
            utility_links = svc.get("utility_links", [])
        else:
            health = await _fetch_health(item.get("health_url"))
            status = _status_from_health(health) if item.get("health_url") else "offline"
            version = "—"
            installed = status == "online"
            watchtower = False
            image = None
            container = item.get("compose_service")
            public_url = item.get("public_url")
            utility_links = []
        if item.get("required"):
            installed = True
        features = portal_features_list() if item["id"] == "portal" else item.get("features", [])
        row = {
            **item,
            "status": status if svc or item.get("health_url") else ("online" if item["id"] == "portal" else "offline"),
            "installed": installed,
            "version": version,
            "watchtower": watchtower,
            "image": image,
            "container": container,
            "public_url": public_url,
            "utility_links": utility_links,
            "features": features,
        }
        row.pop("features_dynamic", None)
        cid = item["id"]
        if cid in _component_defs() and cid not in ("portal", "watchtower"):
            rt = component_runtime_status(cid)
            row["installed"] = rt["installed"]
            row["running"] = rt["running"]
            row["controllable"] = True
            if rt["running"]:
                row["status"] = "online"
                mod_ver = await _fetch_module_version(cid)
                if mod_ver != "—":
                    row["version"] = mod_ver
            else:
                row["status"] = "offline"
        else:
            row["controllable"] = False
        out.append(row)
    return out


def _html_esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_portal_modules_panel() -> str:
    rows = []
    for m in modules_status():
        st = "включён" if m["enabled"] else "отключён"
        cls = "online" if m["enabled"] else "offline"
        checked = "checked" if m["enabled"] else ""
        toggle = (
            f'<label class="toggle" title="{_html_esc(st)}">'
            f'<input type="checkbox" class="mod-toggle" data-module="{_html_esc(m["id"])}" {checked} />'
            f'<span class="toggle-track"><span class="toggle-thumb"></span></span>'
            f"</label>"
        )
        rows.append(
            f'<tr><td>{_html_esc(m["label"])}</td>'
            f'<td><code>{_html_esc(m["path"])}</code></td>'
            f'<td><span class="badge {cls} mod-status" data-module="{_html_esc(m["id"])}">{st}</span></td>'
            f'<td class="toggle-cell">{toggle}</td></tr>'
        )
    return f"""
    <div class="card">
      <h2 class="section-title" style="margin-top:0;">Утилиты внутри портала</h2>
      <p class="muted">Переключателем включите или отключите модуль. Изменение применяется сразу.</p>
      <table class="mod-table">
        <thead><tr><th>Модуль</th><th>Путь</th><th>Статус</th><th>Вкл.</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>"""


def _render_component_card(c: dict[str, Any]) -> str:
    st = c.get("status", "offline")
    badge_cls = "online" if st == "online" else ("offline" if st == "offline" else "degraded")
    installed = c.get("installed")
    role = c.get("role", "")
    role_label = {
        "core": "Ядро",
        "addon": "Модуль",
        "infra": "Инфраструктура",
        "local": "Локальный",
    }.get(role, role)
    features = "".join(f"<li>{_html_esc(f)}</li>" for f in c.get("features", []))
    utils = ""
    if c.get("utility_links"):
        utils = "<ul class='utils'>" + "".join(
            f'<li><a href="{_html_esc(u["path"])}">{_html_esc(u["title"])}</a></li>'
            for u in c["utility_links"]
        ) + "</ul>"
    install = ""
    actions = ""
    if c.get("controllable"):
        cid = c["id"]
        if installed:
            actions = f'<button class="btn sec" data-uninstall="{_html_esc(cid)}">Удалить</button>'
        else:
            actions = f'<button class="btn" data-install="{_html_esc(cid)}">Установить</button>'
    elif not installed and c.get("install_hint"):
        install = (
            f'<p class="install-hint"><b>Установка:</b><br>'
            f'<code>{_html_esc(c["install_hint"])}</code></p>'
        )
    if installed and c.get("public_url"):
        install = f'<p class="muted">Открыть: <a href="{_html_esc(c["public_url"])}" target="_blank" rel="noopener">{_html_esc(c["public_url"])}</a></p>'
    update_btn = ""
    if c.get("watchtower") and installed:
        update_btn = f'<button class="btn sec" data-update="{_html_esc(c["id"])}">Обновить образ</button>'
    pub = "" if c.get("publishable", True) else '<span class="badge local">локальный</span>'
    inst_badge = '<span class="badge online">установлен</span>' if installed else '<span class="badge offline">не установлен</span>'
    meta = ""
    if c.get("container"):
        meta = f'<p class="muted meta">Контейнер: <code>{_html_esc(c["container"])}</code>'
        if c.get("image"):
            meta += f' · Образ: <code>{_html_esc(c["image"])}</code>'
        meta += "</p>"
    return f"""
    <div class="card component-card" data-role="{_html_esc(role)}">
      <div class="svc-head">
        <div>
          <h2>{_html_esc(c.get('icon', ''))} {_html_esc(c['name'])} {pub}</h2>
          <p class="tagline">{_html_esc(c.get('tagline', ''))}</p>
          <p class="muted">{_html_esc(c.get('description', ''))}</p>
          {meta}
        </div>
        <div class="badges-col">
          <span class="badge {badge_cls}">{st}</span>
          {inst_badge}
          <span class="badge role">{_html_esc(role_label)}</span>
        </div>
      </div>
      <p class="ver">Версия: <b>{_html_esc(c.get('version', '—'))}</b></p>
      <ul class="features">{features}</ul>
      {utils}
      {install}
      <div class="actions">{actions} {update_btn}</div>
    </div>"""


def trigger_watchtower_update(scope: str | None = None, image: str | None = None) -> dict[str, Any]:
    from portal.platform_control import compose_service_for_image, compose_update_service

    url = WATCHTOWER_URL
    target_image = image
    if image:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}image={urllib.parse.quote(image, safe='')}"
    elif scope:
        scope_images = {
            "portal": os.getenv("PORTAL_IMAGE", "makeden/portal:latest"),
            "masha": os.getenv("MASHA_IMAGE", "makeden/masha-print:latest"),
            "lisp-calc": "makeden/lisp_calc:latest",
            "norm-control": "makeden/norm_control:latest",
            "convert-to-pdf": "makeden/convert-to-pdf:latest",
        }
        target_image = scope_images.get(scope)
        if target_image:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}image={urllib.parse.quote(target_image, safe='')}"
    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Authorization", f"Bearer {WATCHTOWER_TOKEN}")
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode()
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                pass
            summary = payload.get("summary", {})
            scanned = int(summary.get("scanned", -1))
            updated = int(summary.get("updated", 0))
            if scanned == 0 and target_image:
                service = compose_service_for_image(target_image)
                if service:
                    fb = compose_update_service(service)
                    if fb.get("ok"):
                        return {
                            "ok": True,
                            "message": (
                                f"Watchtower: scanned=0 → обновлено через compose ({service})"
                            ),
                            "via": "compose",
                            "watchtower": payload,
                        }
                    return {
                        "ok": False,
                        "error": fb.get("error", "compose update failed"),
                        "via": "compose",
                        "watchtower": payload,
                    }
            msg = "Watchtower: проверка обновлений запущена"
            if target_image:
                msg += f" (image={target_image})"
            if scanned >= 0:
                msg += f", scanned={scanned}, updated={updated}"
            return {"ok": True, "status": resp.status, "message": msg, "watchtower": payload}
    except Exception as e:
        err = str(e).lower()
        if target_image and ("timed out" in err or "reset" in err):
            service = compose_service_for_image(target_image)
            if service:
                fb = compose_update_service(service)
                if fb.get("ok"):
                    return {
                        "ok": True,
                        "message": f"Watchtower timeout → обновлено через compose ({service})",
                        "via": "compose",
                    }
        if "timed out" in err or "reset" in err:
            return {"ok": True, "message": "Обновление запущено в фоне (watchtower)"}
        if target_image:
            service = compose_service_for_image(target_image)
            if service:
                fb = compose_update_service(service)
                if fb.get("ok"):
                    return {
                        "ok": True,
                        "message": f"Watchtower недоступен → обновлено через compose ({service})",
                        "via": "compose",
                    }
                return {"ok": False, "error": fb.get("error", str(e)), "via": "compose"}
        return {"ok": False, "error": str(e)}


@router.get("/services", response_class=HTMLResponse)
async def services_page():
    components = await build_platform_components()
    portal_ver = _portal_version()
    published = [c for c in components if c.get("publishable")]
    local = [c for c in components if not c.get("publishable")]
    intro = (
        f"<p>На сервере: <b>{sum(1 for c in published if c.get('installed'))}</b> из "
        f"<b>{len(published)}</b> публикуемых компонентов установлено. "
        f"Портал v<b>{_html_esc(portal_ver)}</b>.</p>"
    )
    local_section = ""
    if local:
        local_section = (
            "<h2 class='section-title'>Локальные модули (только ваш сервер)</h2>"
            + "".join(_render_component_card(c) for c in local)
        )
    html = _SERVICES_HTML.replace("{{INTRO}}", intro)
    html = html.replace("{{PORTAL_MODULES}}", _render_portal_modules_panel())
    html = html.replace("{{CARDS_PUBLISHED}}", "".join(_render_component_card(c) for c in published))
    html = html.replace("{{CARDS_LOCAL}}", local_section)
    html = html.replace("{{PORTAL_VERSION}}", _html_esc(portal_ver))
    return html


@router.get("/api/services")
async def api_services_list():
    services = await build_services_status()
    components = await build_platform_components()
    return JSONResponse(
        {
            "platform": "road-platform",
            "portal_version": _portal_version(),
            "services": services,
            "components": components,
        }
    )


@router.get("/api/components")
async def api_components_list():
    return JSONResponse(
        {
            "platform": "road-platform",
            "portal_version": _portal_version(),
            "components": await build_platform_components(),
        }
    )


@router.post("/api/services/update/{service_id}")
async def api_service_update(service_id: str):
    services = get_services_config()
    svc = next((s for s in services if s["id"] == service_id), None)
    if not svc:
        return JSONResponse(status_code=404, content={"error": "Сервис не найден"})
    if not svc.get("watchtower"):
        return JSONResponse(
            status_code=400,
            content={"error": "Этот компонент не обновляется через Watchtower"},
        )
    scope = svc.get("watchtower_scope")
    image = svc.get("image")
    result = trigger_watchtower_update(scope=scope, image=image)
    result["service_id"] = service_id
    result["container"] = svc.get("container")
    scope_hint = f" scope={scope}" if scope else ""
    result["note"] = (
        f"Watchtower обновит контейнер {svc.get('container')}{scope_hint}, "
        "если на registry есть новый образ."
    )
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


@router.post("/api/services/update-all")
async def api_update_all():
    result = trigger_watchtower_update()
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


@router.post("/api/components/{component_id}/install")
async def api_component_install(component_id: str):
    result = install_component(component_id)
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


@router.post("/api/components/{component_id}/uninstall")
async def api_component_uninstall(component_id: str):
    result = uninstall_component(component_id)
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


@router.post("/api/portal/modules/{module_id}")
async def api_portal_module_toggle(
    module_id: str,
    body: dict = Body(default={"enabled": True}),
):
    enabled = bool(body.get("enabled", True))
    result = set_portal_module(module_id, enabled)
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


_SERVICES_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Компоненты платформы</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { --card:#111827; --accent:#38bdf8; --text:#e5e7eb; --soft:#9ca3af; --ok:#4ade80; --err:#f87171; --warn:#fbbf24; }
    body { margin:0; font-family:system-ui,sans-serif; background:radial-gradient(circle at top,#1e293b,#020617); color:var(--text); min-height:100vh; }
    .wrap { max-width:960px; margin:0 auto; padding:24px 20px 48px; }
    a { color:var(--accent); }
    .hero { background:linear-gradient(135deg,rgba(56,189,248,.12),rgba(15,23,42,.9)); border:1px solid rgba(56,189,248,.25); border-radius:20px; padding:24px; margin:16px 0 24px; }
    .hero h1 { margin:0 0 8px; font-size:26px; }
    .hero p { margin:0; color:var(--soft); line-height:1.55; font-size:14px; }
  .card { background:var(--card); border:1px solid rgba(148,163,184,.3); border-radius:16px; padding:20px; margin-bottom:16px; }
    .section-title { font-size:18px; margin:28px 0 12px; color:var(--accent); }
    .svc-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
    .badges-col { display:flex; flex-direction:column; gap:6px; align-items:flex-end; }
    .component-card h2 { margin:0; font-size:18px; color:var(--accent); }
    .tagline { margin:6px 0 0; font-size:13px; color:var(--soft); font-style:italic; }
    .badge { font-size:11px; padding:3px 8px; border-radius:6px; display:inline-block; }
    .online { background:rgba(74,222,128,.15); color:var(--ok); }
    .offline { background:rgba(248,113,113,.15); color:var(--err); }
    .degraded { background:rgba(251,191,36,.15); color:var(--warn); }
    .local { background:rgba(148,163,184,.15); color:var(--soft); }
    .role { background:rgba(56,189,248,.12); color:var(--accent); }
    .btn { background:var(--accent); color:#000; border:none; padding:8px 14px; border-radius:8px; font-weight:600; cursor:pointer; margin-top:12px; }
    .btn.sec { background:transparent; border:1px solid var(--accent); color:var(--accent); }
    .muted { color:var(--soft); font-size:13px; }
    .meta { margin-top:8px; }
    .ver { margin:12px 0 8px; font-size:14px; }
    ul.features, ul.utils { margin:8px 0 0; padding-left:18px; font-size:13px; line-height:1.6; }
    .install-hint { margin-top:12px; font-size:13px; background:#0f172a; border-radius:8px; padding:12px; border:1px dashed rgba(148,163,184,.4); }
    .install-hint code { font-size:12px; word-break:break-all; }
    .toolbar { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:8px; }
    .mod-table { width:100%; border-collapse:collapse; font-size:13px; margin:12px 0; }
    .mod-table th, .mod-table td { text-align:left; padding:8px 10px; border-bottom:1px solid rgba(148,163,184,.2); }
    .mod-table th { color:var(--soft); font-weight:600; }
    .toggle-cell { width:72px; }
    .toggle { position:relative; display:inline-flex; align-items:center; cursor:pointer; }
    .toggle input { position:absolute; opacity:0; width:0; height:0; }
    .toggle-track {
      width:44px; height:24px; background:rgba(248,113,113,.35); border-radius:999px;
      position:relative; transition:background .2s;
    }
    .toggle input:checked + .toggle-track { background:rgba(74,222,128,.45); }
    .toggle-thumb {
      position:absolute; top:3px; left:3px; width:18px; height:18px; border-radius:50%;
      background:#e5e7eb; transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.35);
    }
    .toggle input:checked + .toggle-track .toggle-thumb { transform:translateX(20px); background:#4ade80; }
    .toggle input:disabled + .toggle-track { opacity:.45; cursor:wait; }
    .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  </style>
</head>
<body>
  <div class="wrap">
    <a href="/">← На главную</a>
    <div class="hero">
      <h1>Компоненты платформы</h1>
      <p>
        Поднимаете <b>портал</b> — выбираете модули — Docker запускает контейнеры.
        <b>Watchtower</b> следит за обновлениями образов на Docker Hub.
      </p>
      <div class="intro-stats muted" style="margin-top:12px;">{{INTRO}}</div>
    </div>
    <div class="toolbar card">
      <button class="btn" id="btn-all">Обновить все (Watchtower)</button>
      <button class="btn sec" id="btn-refresh">Обновить статус</button>
      <span class="muted">Портал v{{PORTAL_VERSION}}</span>
    </div>
    {{PORTAL_MODULES}}
    <h2 class="section-title">Публикуемые компоненты</h2>
    <div id="published-grid">{{CARDS_PUBLISHED}}</div>
    {{CARDS_LOCAL}}
  </div>
  <script>
    async function apiPost(url, confirmText) {
      if (confirmText && !confirm(confirmText)) return;
      const r = await fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: "{}" });
      const j = await r.json();
      alert(j.message || j.note || j.error || JSON.stringify(j));
      if (j.ok !== false && r.ok) setTimeout(() => location.reload(), j.action === "install" || j.portal_modules ? 3000 : 1500);
    }
    document.querySelectorAll("[data-update]").forEach(btn => {
      btn.onclick = () => apiPost("/api/services/update/" + btn.dataset.update, "Обновить образ через Watchtower?");
    });
    document.querySelectorAll("[data-install]").forEach(btn => {
      btn.onclick = () => apiPost("/api/components/" + btn.dataset.install + "/install", "Установить компонент " + btn.dataset.install + "?");
    });
    document.querySelectorAll("[data-uninstall]").forEach(btn => {
      btn.onclick = () => apiPost("/api/components/" + btn.dataset.uninstall + "/uninstall", "Удалить компонент " + btn.dataset.uninstall + "?");
    });
    document.querySelectorAll(".mod-toggle").forEach(inp => {
      inp.addEventListener("change", async () => {
        const en = inp.checked;
        const mid = inp.dataset.module;
        const label = inp.closest("tr")?.querySelector("td")?.textContent?.trim() || mid;
        if (!confirm((en ? "Включить" : "Отключить") + " «" + label + "»?")) {
          inp.checked = !en;
          return;
        }
        inp.disabled = true;
        try {
          const r = await fetch("/api/portal/modules/" + mid, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ enabled: en })
          });
          const j = await r.json();
          if (!r.ok || j.ok === false) {
            inp.checked = !en;
            alert(j.error || j.message || "Ошибка переключения модуля");
            return;
          }
          const badge = document.querySelector('.mod-status[data-module="' + mid + '"]');
          if (badge) {
            badge.textContent = en ? "включён" : "отключён";
            badge.classList.toggle("online", en);
            badge.classList.toggle("offline", !en);
          }
          setTimeout(() => location.reload(), 800);
        } catch (e) {
          inp.checked = !en;
          alert("Ошибка: " + e);
        } finally {
          inp.disabled = false;
        }
      });
    });
    document.getElementById("btn-all").onclick = async () => {
      if (!confirm("Обновить все контейнеры с меткой Watchtower?")) return;
      const j = await fetch("/api/services/update-all", { method: "POST" }).then(r => r.json());
      alert(j.message || j.error || "Готово");
    };
    document.getElementById("btn-refresh").onclick = () => location.reload();
  </script>
</body>
</html>"""
