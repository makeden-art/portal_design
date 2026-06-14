"""Проксирование /calc и /norm на отдельные контейнеры-модули."""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from portal.module_services import MODULE_SERVICES
from portal.modules import is_module_enabled

CALC_URL = os.getenv("CALC_SERVICE_URL", "http://lisp-calc:8000").rstrip("/")
NORM_URL = os.getenv("NORM_SERVICE_URL", "http://norm-control:8000").rstrip("/")
CONVERT_URL = os.getenv("CONVERT_SERVICE_URL", "http://convert-to-pdf:8000").rstrip("/")

_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def setup_service_proxies(app: FastAPI) -> None:
    @app.api_route("/calc", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    @app.api_route("/calc/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    async def proxy_calc(request: Request, path: str = "") -> Response:
        return await _proxy(request, "calc", CALC_URL, path)

    @app.api_route("/process", methods=["POST"], include_in_schema=False)
    async def proxy_calc_process(request: Request) -> Response:
        return await _proxy(request, "calc", CALC_URL, "process")

    @app.api_route("/download/{token}", methods=["GET"], include_in_schema=False)
    async def proxy_calc_download(request: Request, token: str) -> Response:
        return await _proxy(request, "calc", CALC_URL, f"download/{token}")

    @app.api_route("/norm", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    @app.api_route("/norm/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    async def proxy_norm(request: Request, path: str = "") -> Response:
        return await _proxy(request, "norm", NORM_URL, path)

    @app.api_route("/process_norm", methods=["POST"], include_in_schema=False)
    async def proxy_norm_api(request: Request) -> Response:
        return await _proxy(request, "norm", NORM_URL, "process_norm")

    @app.api_route("/convert", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    @app.api_route("/convert/{path:path}", methods=["GET", "POST", "HEAD", "OPTIONS"], include_in_schema=False)
    async def proxy_convert(request: Request, path: str = "") -> Response:
        sub = f"convert/{path}" if path else "convert"
        return await _proxy(request, "convert", CONVERT_URL, sub)

    @app.api_route("/api/convert", methods=["POST"], include_in_schema=False)
    async def proxy_convert_api(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/convert")

    @app.api_route("/api/convert-folder", methods=["POST"], include_in_schema=False)
    async def proxy_convert_folder_api(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/convert-folder")

    @app.api_route("/api/convert-folder-form", methods=["POST"], include_in_schema=False)
    async def proxy_convert_folder_form(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/convert-folder-form")

    @app.api_route("/api/convert-merge", methods=["POST"], include_in_schema=False)
    async def proxy_convert_merge(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/convert-merge")

    @app.api_route("/api/browse", methods=["GET"], include_in_schema=False)
    async def proxy_convert_browse(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/browse")

    @app.api_route("/api/convert-paths", methods=["POST"], include_in_schema=False)
    async def proxy_convert_paths(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/convert-paths")

    @app.api_route("/api/resolve-paths", methods=["POST"], include_in_schema=False)
    async def proxy_resolve_paths(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/resolve-paths")

    @app.api_route("/api/check-output", methods=["POST"], include_in_schema=False)
    async def proxy_check_output(request: Request) -> Response:
        return await _proxy(request, "convert", CONVERT_URL, "api/check-output")


async def _proxy(request: Request, module: str, base: str, path: str) -> Response:
    if not is_module_enabled(module):
        raise HTTPException(status_code=404, detail=f"Модуль «{module}» отключён")

    target = f"{base}/{path}" if path else base + request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_HEADERS
    }
    body = await request.body()

    try:
        timeout = 1800.0 if module == "convert" else 300.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.request(
                request.method,
                target,
                headers=headers,
                content=body if body else None,
            )
    except httpx.ConnectError:
        service = MODULE_SERVICES.get(module, module)
        raise HTTPException(
            status_code=503,
            detail=f"Сервис «{module}» не запущен. Включите модуль на /services (контейнер {service}).",
        ) from None
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка сервиса {module}: {e}") from e

    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _HOP_HEADERS
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)
