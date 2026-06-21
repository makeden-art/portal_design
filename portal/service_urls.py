"""URL модулей с запасными адресами (сеть Docker, имя контейнера, порт на хосте)."""
from __future__ import annotations

import os


def _uniq(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        u = (raw or "").strip().rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def module_base_urls(module: str) -> list[str]:
    if module == "calc":
        return _uniq(
            [
                os.getenv("CALC_SERVICE_URL", "http://lisp-calc:8000"),
                "http://lisp-calc-service:8000",
                os.getenv("CALC_FALLBACK_URL", "http://host.docker.internal:8082"),
            ]
        )
    if module == "norm":
        return _uniq(
            [
                os.getenv("NORM_SERVICE_URL", "http://norm-control:8000"),
                "http://norm-control-service:8000",
                os.getenv("NORM_FALLBACK_URL", "http://host.docker.internal:8083"),
            ]
        )
    if module == "convert":
        return _uniq(
            [
                os.getenv("CONVERT_SERVICE_URL", "http://convert-to-pdf:8000"),
                "http://convert-to-pdf-service:8000",
                os.getenv("CONVERT_FALLBACK_URL", "http://host.docker.internal:8084"),
            ]
        )
    return []


def component_base_urls(component_id: str) -> list[str]:
    mapping = {
        "lisp-calc": "calc",
        "norm-control": "norm",
        "convert-to-pdf": "convert",
    }
    mod = mapping.get(component_id)
    return module_base_urls(mod) if mod else []
