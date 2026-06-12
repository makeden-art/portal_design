"""Карточки модулей портала (calc, norm) — без встроенной логики утилит."""
from __future__ import annotations

from fastapi import FastAPI

from portal.modules import register_plugin
from portal.proxy import setup_service_proxies

MODULE_IDS: tuple[str, ...] = ("calc", "norm", "convert")

MODULE_CARDS: dict[str, dict[str, str]] = {
    "calc": {
        "href": "/calc",
        "title": "🏗️ Калькулятор Поперечников",
        "text": "Расчёт объёмов из DXF/DWG. Контейнер: репозиторий lisp_Nikolay.",
    },
    "norm": {
        "href": "/norm",
        "title": "📏 Нормоконтроль (Пакетный)",
        "text": "Проверка оформления по ГОСТ. Контейнер: Documentation-compliance-control.",
    },
    "convert": {
        "href": "/convert",
        "title": "📄 Convert to PDF",
        "text": "Конвертация документов в PDF. Репозиторий Convert-to-PDF.",
    },
}

MODULE_LABELS = {
    "calc": "Поперечники",
    "norm": "Нормоконтроль",
    "convert": "Convert to PDF",
}

MODULE_FEATURES = {
    "calc": "Калькулятор поперечников (lisp_Nikolay)",
    "norm": "Нормоконтроль пакетный (doc-compliance)",
    "convert": "Конвертация в PDF (Convert-to-PDF)",
}

def register(app: FastAPI) -> None:
    register_plugin(
        plugin_id="platform_hub",
        modules=MODULE_IDS,
        cards=MODULE_CARDS,
        labels=MODULE_LABELS,
        features=MODULE_FEATURES,
    )
    setup_service_proxies(app)
