"""Связь модулей портала с docker-compose сервисами."""
from __future__ import annotations

MODULE_SERVICES: dict[str, str] = {
    "calc": "lisp-calc",
    "norm": "norm-control",
}
