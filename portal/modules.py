"""
Реестр модулей портала. Карточки и маршруты регистрируют плагины (lisp_Nikolay и др.).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_PLUGIN_REGISTRY: list[dict[str, Any]] = []

MODULE_CARDS: dict[str, dict[str, str]] = {}
MODULE_LABELS: dict[str, str] = {}
MODULE_FEATURES: dict[str, str] = {}
ALL_MODULES: tuple[str, ...] = ()


def register_plugin(
    *,
    plugin_id: str,
    modules: tuple[str, ...],
    cards: dict[str, dict[str, str]],
    labels: dict[str, str],
    features: dict[str, str],
) -> None:
    """Регистрация модуля-плагина (например lisp_Nikolay)."""
    global ALL_MODULES
    _PLUGIN_REGISTRY.append(
        {
            "plugin_id": plugin_id,
            "modules": modules,
            "cards": cards,
            "labels": labels,
            "features": features,
        }
    )
    MODULE_CARDS.update(cards)
    MODULE_LABELS.update(labels)
    MODULE_FEATURES.update(features)
    ALL_MODULES = tuple(dict.fromkeys((*ALL_MODULES, *modules)))


def _state_modules() -> set[str] | None:
    root = Path(os.getenv("PLATFORM_INSTALL_ROOT", "/opt/road-pdf-platform"))
    state_path = root / "platform.state.json"
    if not state_path.exists():
        return None
    try:
        import json

        data = json.loads(state_path.read_text(encoding="utf-8"))
        mods = data.get("portal_modules")
        if mods:
            return {m for m in mods if m in ALL_MODULES}
    except Exception:
        pass
    return None


def get_enabled_modules() -> set[str]:
    from_state = _state_modules()
    if from_state is not None:
        return from_state
    raw = os.getenv("PORTAL_MODULES", "").strip()
    if not raw:
        return set(ALL_MODULES)
    enabled = {m.strip().lower() for m in raw.split(",") if m.strip()}
    return enabled & set(ALL_MODULES)


def is_module_enabled(name: str) -> bool:
    return name in get_enabled_modules()


def utility_links() -> list[dict[str, str]]:
    links = []
    for mid in ALL_MODULES:
        if is_module_enabled(mid) and mid in MODULE_CARDS:
            links.append({"title": MODULE_LABELS[mid], "path": MODULE_CARDS[mid]["href"]})
    return links


def hub_cards_html() -> str:
    parts = []
    for mid in ALL_MODULES:
        if not is_module_enabled(mid) or mid not in MODULE_CARDS:
            continue
        c = MODULE_CARDS[mid]
        parts.append(
            f'<a href="{c["href"]}" class="card">'
            f'<h2>{c["title"]}</h2><p>{c["text"]}</p></a>'
        )
    parts.append(
        '<a href="/services" class="card">'
        "<h2>⚙️ Компоненты платформы</h2>"
        "<p>Каталог модулей: что установлено, утилиты портала, обновления.</p></a>"
    )
    return "\n".join(parts)


def portal_features_list() -> list[str]:
    return [MODULE_FEATURES[mid] for mid in ALL_MODULES if is_module_enabled(mid) and mid in MODULE_FEATURES]


def modules_status() -> list[dict[str, Any]]:
    enabled = get_enabled_modules()
    return [
        {
            "id": mid,
            "label": MODULE_LABELS.get(mid, mid),
            "enabled": mid in enabled,
            "path": MODULE_CARDS.get(mid, {}).get("href", ""),
        }
        for mid in ALL_MODULES
    ]


def modules_config_hint() -> str:
    enabled = ",".join(mid for mid in ALL_MODULES if is_module_enabled(mid))
    return (
        f"PORTAL_MODULES={enabled}  # в docker-compose.platform.yml → portal → environment, "
        "затем: docker compose -f docker-compose.platform.yml up -d portal"
    )


def registered_plugins() -> list[dict[str, Any]]:
    return [
        {"plugin_id": p["plugin_id"], "modules": list(p["modules"])}
        for p in _PLUGIN_REGISTRY
    ]
