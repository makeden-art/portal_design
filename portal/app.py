"""Ядро портала: хаб, обновления, страница сервисов."""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from portal.modules import hub_cards_html, is_module_enabled, modules_status
from portal.platform_control import _load_state, _sync_runtime_env
from portal.services_hub import router as services_hub_router
from portal.smb_mount import mount_smb, remount_from_state, smb_status, unmount_smb
from portal.update_check import check_all_updates, check_portal_update, portal_version

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class SmbMountRequest(BaseModel):
    server: str
    share: str
    username: str = ""
    password: str = ""
    domain: str = ""
    anonymous: bool = False
    mount_id: str = "default"


def get_current_version() -> str:
    return portal_version()


def create_app() -> FastAPI:
    app = FastAPI(title="Инженерные Утилиты")
    app.include_router(services_hub_router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        _load_plugins(app)
        try:
            _sync_runtime_env(_load_state())
        except Exception:
            pass
        def _bg_remount() -> None:
            try:
                remount_from_state()
            except Exception:
                pass

        threading.Thread(target=_bg_remount, daemon=True).start()

    @app.get("/api/platform/smb/status")
    async def api_smb_status():
        return JSONResponse(await asyncio.to_thread(smb_status))

    @app.post("/api/platform/smb/mount")
    async def api_smb_mount(payload: SmbMountRequest):
        try:
            result = await asyncio.to_thread(
                mount_smb,
                server=payload.server,
                share=payload.share,
                username=payload.username,
                password=payload.password,
                domain=payload.domain,
                anonymous=payload.anonymous,
                mount_id=payload.mount_id,
            )
            return JSONResponse(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post("/api/platform/smb/unmount")
    async def api_smb_unmount():
        try:
            return JSONResponse(await asyncio.to_thread(unmount_smb))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/api/portal/modules")
    async def api_portal_modules():
        return JSONResponse({"modules": modules_status()})

    @app.get("/version")
    async def version():
        return JSONResponse({"version": get_current_version(), "service": "portal"})

    @app.get("/api/check_update")
    async def check_update():
        return JSONResponse(check_portal_update())

    @app.get("/api/check_updates")
    async def check_updates():
        return JSONResponse(await check_all_updates())

    @app.post("/api/do_update")
    async def do_update():
        from portal.services_hub import trigger_watchtower_update

        portal_image = os.getenv("PORTAL_IMAGE", "makeden/portal:latest")
        result = trigger_watchtower_update(image=portal_image)
        status = 200 if result.get("ok") else 500
        return JSONResponse(
            status_code=status,
            content={
                "status": "ok" if result.get("ok") else "error",
                "message": result.get("message") or result.get("error", ""),
                **result,
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def hub() -> str:
        html = """
    <!DOCTYPE html>
    <html lang="ru">
      <head>
        <meta charset="utf-8" />
        <title>Инженерные Утилиты</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="stylesheet" href="/static/theme.css" />
        <style>
          body { display: flex; flex-direction: column; align-items: center; justify-content: center; }
          .hub-container { max-width: 800px; width: 100%; padding: 20px; }
          .title { text-align: center; margin-bottom: 40px; }
          .title h1 { margin: 0 0 10px 0; }
          .title p { color: var(--text-soft); margin: 0; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
          .card {
            background: var(--bg-card); border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 20px; padding: 24px; text-decoration: none; color: var(--text);
            transition: all 0.2s ease; display: flex; flex-direction: column; gap: 12px;
          }
          .card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.3); }
          .card h2 { margin: 0; font-size: 20px; color: var(--accent); }
          .card p { margin: 0; color: var(--text-soft); font-size: 14px; line-height: 1.5; }
          .footer { text-align: center; margin-top: 40px; color: var(--text-soft); font-size: 12px; }
          .update-banner {
            background: linear-gradient(90deg, rgba(34, 197, 94, 0.15), rgba(16, 185, 129, 0.05));
            border: 1px solid rgba(34, 197, 94, 0.4);
            border-radius: 14px; padding: 14px 18px; margin-bottom: 24px;
            display: none; justify-content: space-between; align-items: center; gap: 16px;
          }
          .primary-btn {
            background: var(--accent); color: #000; border: none; padding: 8px 16px;
            border-radius: 8px; font-weight: 600; cursor: pointer;
          }
          .primary-btn:disabled { opacity: 0.5; }
          .update-badge {
            align-self: flex-start; font-size: 11px; font-weight: 600;
            background: rgba(34, 197, 94, 0.2); color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.5); border-radius: 999px;
            padding: 2px 8px; margin-bottom: 4px;
          }
          .card.has-update { border-color: rgba(34, 197, 94, 0.55); }
          .update-actions { display: flex; gap: 8px; flex-wrap: wrap; }
          .sec-btn {
            background: transparent; color: var(--accent); border: 1px solid var(--accent);
            padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer;
            text-decoration: none; font-size: 14px;
          }
        </style>
      </head>
      <body class="portal">
        <div class="hub-container portal-container">
          <div id="update-banner" class="update-banner">
            <span id="update-text" style="font-size: 14px;"></span>
            <div class="update-actions">
              <a href="/services" id="btn-services" class="sec-btn" style="display:none;">Сервисы →</a>
              <button id="btn-do-update" class="primary-btn" style="display:none;">Обновить портал</button>
            </div>
          </div>
          <div class="title">
            <h1>Инженерные Утилиты</h1>
            <p>Выберите нужный инструмент для работы</p>
          </div>
          <div class="grid">
            {{HUB_CARDS}}
          </div>
          <div class="footer">Версия портала: <b>v{{VERSION}}</b></div>
        </div>
        <script>
          fetch("/api/check_updates").then(r=>r.json()).then(d=>{
            const parts = [];
            if (d.portal && d.portal.has_update) {
              parts.push("Портал v" + d.portal.remote);
              const btn = document.getElementById("btn-do-update");
              if (btn) btn.style.display = "inline-block";
            }
            (d.modules || []).forEach(m => {
              if (!m.has_update) return;
              parts.push(m.name + " v" + m.remote);
              const card = document.querySelector('[data-module="' + m.id + '"]');
              if (card) {
                card.classList.add("has-update");
                if (!card.querySelector(".update-badge")) {
                  card.insertAdjacentHTML("afterbegin", '<span class="update-badge">доступно обновление</span>');
                }
              }
            });
            if (!parts.length) return;
            document.getElementById("update-text").innerHTML =
              "🚀 Доступны обновления: <b style=\"color:#4ade80\">" + parts.join(", ") + "</b>";
            document.getElementById("update-banner").style.display = "flex";
            const svcBtn = document.getElementById("btn-services");
            if (svcBtn && (d.modules || []).some(m => m.has_update)) svcBtn.style.display = "inline-block";
          });
          const btn = document.getElementById("btn-do-update");
          if(btn){
            btn.onclick = () => {
              if(!confirm("Запустить автоматическое обновление портала? Приложение будет перезапущено.")) return;
              btn.disabled = true; btn.textContent = "Обновление...";
              fetch("/api/do_update", {method: "POST"}).then(r=>r.json()).then(d=>{
                if(d.status==="ok"){ alert("Команда отправлена! Страница перезагрузится через 20 секунд."); setTimeout(()=>location.reload(), 20000); }
                else { alert("Ошибка: "+d.message); btn.disabled=false; btn.textContent="Обновить портал"; }
              }).catch(e=>{ alert("Ошибка: "+e); btn.disabled=false; btn.textContent="Обновить портал"; });
            };
          }
        </script>
      </body>
    </html>
    """
        return html.replace("{{VERSION}}", get_current_version()).replace(
            "{{HUB_CARDS}}", hub_cards_html()
        )

    return app


def _load_plugins(app: FastAPI) -> None:
  import importlib
  for name in os.getenv("PORTAL_PLUGINS", "portal_utilities").split(","):
    name = name.strip()
    if not name:
      continue
    try:
      mod = importlib.import_module(name)
      register = getattr(mod, "register", None)
      if register:
        register(app)
    except ImportError as e:
      import logging
      logging.getLogger("portal").warning("Plugin %s not loaded: %s", name, e)
