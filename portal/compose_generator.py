"""Генерация docker-compose.client.yml из каталога сервисов."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portal.platform_services import (
    DEFAULT_COMPOSE_NAME,
    client_compose_services,
)


@dataclass
class ComposeGenerateOptions:
    root: Path = Path("/opt/road-pdf-platform")
    compose_filename: str = DEFAULT_COMPOSE_NAME
    portal_port: int = 80
    watchtower_token: str = "platform_watchtower_secret"
    network_name: str = "road-platform"
    external_network: bool = False
    project_name: str = "road-platform"


def compose_output_path(opts: ComposeGenerateOptions) -> Path:
    return opts.root / opts.compose_filename


def _indent(level: int) -> str:
    return "  " * level


def _yaml_quote(value: str) -> str:
    if not value:
        return '""'
    if all(c.isalnum() or c in "-_./:" for c in value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dump_scalar(value: Any, level: int) -> list[str]:
    if isinstance(value, bool):
        return [f"{_indent(level)}{'true' if value else 'false'}"]
    if isinstance(value, (int, float)):
        return [f"{_indent(level)}{value}"]
    return [f"{_indent(level)}{_yaml_quote(str(value))}"]


def _dump_list(items: list[Any], level: int) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"{_indent(level)}-")
            lines.extend(_dump_mapping(item, level + 1, root=True))
        else:
            lines.append(f"{_indent(level)}- {_yaml_quote(str(item))}")
    return lines


def _dump_mapping(
    data: dict[str, Any],
    level: int,
    *,
    root: bool = False,
) -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        prefix = _indent(level)
        if value is None:
            lines.append(f"{prefix}{key}: null")
        elif isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_dump_mapping(value, level + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            lines.extend(_dump_list(value, level + 1))
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_quote(str(value))}")
    return lines


def _service_to_dict(spec: Any) -> dict[str, Any]:
    from portal.platform_services import ServiceSpec

    assert isinstance(spec, ServiceSpec)
    svc: dict[str, Any] = {
        "image": spec.image,
        "container_name": spec.container_name,
        "restart": spec.restart,
    }
    if spec.ports:
        svc["ports"] = list(spec.ports)
    if spec.environment:
        svc["environment"] = list(spec.environment)
    if spec.volumes:
        svc["volumes"] = list(spec.volumes)
    if spec.labels:
        svc["labels"] = dict(spec.labels)
    if spec.networks:
        svc["networks"] = list(spec.networks)
    if spec.profile:
        svc["profiles"] = [spec.profile]
    return svc


def build_compose_document(opts: ComposeGenerateOptions) -> dict[str, Any]:
    compose_path = compose_output_path(opts)
    services = client_compose_services(
        root=opts.root,
        compose_path=compose_path,
        portal_port=opts.portal_port,
        watchtower_token=opts.watchtower_token,
    )
    network: dict[str, Any] = {"name": opts.network_name}
    if opts.external_network:
        network["external"] = True

    doc: dict[str, Any] = {
        "name": opts.project_name,
        "services": {sid: _service_to_dict(spec) for sid, spec in services.items()},
        "networks": {opts.network_name: network},
        "volumes": {"convert-data": None},
    }
    return doc


def generate_compose_yaml(opts: ComposeGenerateOptions) -> str:
    doc = build_compose_document(opts)
    lines = [
        "# Автогенерация: python -m portal.compose_cli bootstrap",
        "# Источник: portal.platform_services + portal.compose_generator",
        "",
        f"name: {doc['name']}",
        "",
        "services:",
    ]
    for svc_name, svc_body in doc["services"].items():
        lines.append(f"  {svc_name}:")
        lines.extend(_dump_mapping(svc_body, 2))
        lines.append("")

    lines.append("networks:")
    lines.extend(_dump_mapping(doc["networks"], 1))
    lines.append("")
    lines.append("volumes:")
    lines.extend(_dump_mapping(doc["volumes"], 1))
    lines.append("")
    return "\n".join(lines)


def write_compose_file(opts: ComposeGenerateOptions, *, force: bool = False) -> Path:
    path = compose_output_path(opts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path
    path.write_text(generate_compose_yaml(opts), encoding="utf-8")
    return path
