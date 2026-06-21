"""Каталог сервисов платформы — единый источник для compose и UI."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("/opt/road-pdf-platform")
DEFAULT_COMPOSE_NAME = "docker-compose.client.yml"
DEFAULT_WATCHTOWER_TOKEN = "platform_watchtower_secret"
DOCKER_HUB = os.getenv("PLATFORM_DOCKER_HUB", "makeden")


@dataclass(frozen=True)
class ServiceSpec:
    """Описание docker-compose сервиса (клиентский профиль — только image, без build)."""

    id: str
    image: str
    container_name: str
    ports: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    volumes: tuple[Any, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    networks: tuple[str, ...] = ("road-platform",)
    restart: str = "unless-stopped"
    client_compose: bool = True
    command: tuple[str, ...] | None = None
    no_uninstall: bool = False
    profile: str | None = None
    publishable: bool = True


def _hub(image: str) -> str:
    return f"{DOCKER_HUB}/{image}"


def service_catalog(
    *,
    root: Path = DEFAULT_ROOT,
    compose_path: Path | None = None,
    portal_port: int = 80,
    watchtower_token: str = DEFAULT_WATCHTOWER_TOKEN,
) -> dict[str, ServiceSpec]:
    """Все сервисы платформы для генерации клиентского compose."""
    root = root.resolve()
    compose_file = compose_path or (root / DEFAULT_COMPOSE_NAME)
    compose_env = str(compose_file)
    root_s = str(root)

    portal_env = (
        f"WATCHTOWER_URL=http://watchtower:8080/v1/update",
        f"WATCHTOWER_TOKEN={watchtower_token}",
        f"PORTAL_IMAGE={_hub('portal:latest')}",
        "CALC_SERVICE_URL=http://lisp-calc:8000",
        "NORM_SERVICE_URL=http://norm-control:8000",
        "CONVERT_SERVICE_URL=http://convert-to-pdf:8000",
        "CALC_FALLBACK_URL=http://host.docker.internal:8082",
        "NORM_FALLBACK_URL=http://host.docker.internal:8083",
        "CONVERT_FALLBACK_URL=http://host.docker.internal:8084",
        f"PLATFORM_INSTALL_ROOT={root_s}",
        f"PLATFORM_COMPOSE_FILE={compose_env}",
        "PORTAL_MODULES=calc,norm,convert",
        "PORTAL_PLUGINS=portal.hub_modules",
        "DOCKER_COMPOSE_BIN=/usr/local/bin/docker-compose",
    )

    return {
        "portal": ServiceSpec(
            id="portal",
            image=_hub("portal:latest"),
            container_name="geo_calc_app",
            ports=(f"{portal_port}:8000",),
            environment=portal_env,
            volumes=(
                "/var/run/docker.sock:/var/run/docker.sock",
                "/usr/bin/docker:/usr/local/bin/docker:ro",
                f"{root_s}:{root_s}",
            ),
            labels={"com.centurylinklabs.watchtower.enable": "true"},
            no_uninstall=True,
        ),
        "watchtower": ServiceSpec(
            id="watchtower",
            image="nickfedor/watchtower:latest",
            container_name="watchtower",
            environment=(
                "DOCKER_API_VERSION=1.44",
                "WATCHTOWER_HTTP_API_UPDATE=true",
                f"WATCHTOWER_HTTP_API_TOKEN={watchtower_token}",
                "WATCHTOWER_CLEANUP=true",
                "WATCHTOWER_POLL_INTERVAL=3600",
                "WATCHTOWER_LABEL_ENABLE=true",
            ),
            volumes=("/var/run/docker.sock:/var/run/docker.sock",),
            labels={"com.centurylinklabs.watchtower.enable": "false"},
            no_uninstall=True,
        ),
        "lisp-calc": ServiceSpec(
            id="lisp-calc",
            image=_hub("lisp_calc:latest"),
            container_name="lisp-calc-service",
            ports=("8082:8000",),
            labels={"com.centurylinklabs.watchtower.enable": "true"},
        ),
        "norm-control": ServiceSpec(
            id="norm-control",
            image=_hub("norm_control:latest"),
            container_name="norm-control-service",
            ports=("8083:8000",),
            labels={"com.centurylinklabs.watchtower.enable": "true"},
        ),
        "convert-to-pdf": ServiceSpec(
            id="convert-to-pdf",
            image=_hub("convert-to-pdf:latest"),
            container_name="convert-to-pdf-service",
            ports=("8084:8000",),
            environment=(
                f"CONVERT_ALLOWED_ROOTS=/data,/workspace,{root_s}",
                "CONVERT_UVICORN_CONCURRENCY=16",
                "CONVERT_CHILD_MEM_MB=3072",
                "CONVERT_MERGE_WORKERS=1",
            ),
            command=(
                "sh",
                "-c",
                "exec uvicorn app:app --host 0.0.0.0 --port 8000 --limit-concurrency ${CONVERT_UVICORN_CONCURRENCY:-16}",
            ),
            volumes=(
                "convert-data:/data",
                f"{root_s}:{root_s}",
            ),
            labels={"com.centurylinklabs.watchtower.enable": "true"},
        ),
        "masha-print": ServiceSpec(
            id="masha-print",
            image=_hub("masha-print:latest"),
            container_name=os.getenv("MASHA_CONTAINER", "masha-print-service"),
            client_compose=False,
        ),
    }


def component_runtime_defs(
  root: Path | None = None,
  masha_container: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Метаданные для platform_control (установка / статус контейнеров)."""
    catalog = service_catalog(root=root or DEFAULT_ROOT)
    out: dict[str, dict[str, Any]] = {}
    for sid, spec in catalog.items():
        if masha_container and sid == "masha-print":
            container = masha_container
        else:
            container = spec.container_name
        out[sid] = {
            "service": spec.id,
            "container": container,
            "profile": spec.profile,
            "publishable": spec.publishable,
            "no_uninstall": spec.no_uninstall,
        }
    return out


def client_compose_services(
    *,
    root: Path = DEFAULT_ROOT,
    compose_path: Path | None = None,
    portal_port: int = 80,
    watchtower_token: str = DEFAULT_WATCHTOWER_TOKEN,
) -> dict[str, ServiceSpec]:
    """Сервисы, попадающие в автогенерируемый клиентский compose."""
    catalog = service_catalog(
        root=root,
        compose_path=compose_path,
        portal_port=portal_port,
        watchtower_token=watchtower_token,
    )
    return {k: v for k, v in catalog.items() if v.client_compose}
