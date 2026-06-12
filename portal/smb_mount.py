"""Подключение SMB/CIFS с хоста через privileged Docker + nsenter."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from portal.platform_control import PLATFORM_ROOT, _load_state, _save_state

SECRETS_DIR = PLATFORM_ROOT / "secrets" / "smb"
MNT_ROOT = PLATFORM_ROOT / "mnt" / "smb"
MOUNT_HELPER_IMAGE = "debian:bookworm-slim"

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def _validate_server(server: str) -> str:
    server = server.strip()
    if not server or "/" in server or "\\" in server:
        raise ValueError("Укажите имя или IP сервера SMB без слэшей")
    return server


def _validate_share(share: str) -> str:
    share = share.strip().strip("/")
    if not share or ".." in share:
        raise ValueError("Укажите имя шары без .. и слэшей")
    return share


def _validate_mount_id(mount_id: str) -> str:
    mount_id = (mount_id or "default").strip()
    if not _SAFE_ID.match(mount_id):
        raise ValueError("Идентификатор монтирования: латиница, цифры, _ и - (до 32 символов)")
    return mount_id


def _mount_path(mount_id: str) -> Path:
    return MNT_ROOT / mount_id


def _creds_path(mount_id: str) -> Path:
    return SECRETS_DIR / f"{mount_id}.creds"


def smb_status() -> dict[str, Any]:
    state = _load_state()
    info = state.get("smb_mount") or {}
    mount_path = info.get("mount_path")
    mounted = False
    if mount_path:
        try:
            proc = subprocess.run(
                ["docker", "run", "--rm", "--privileged", "--pid=host", MOUNT_HELPER_IMAGE, "bash", "-c",
                 f"apt-get update -qq && apt-get install -y -qq util-linux >/dev/null && "
                 f"nsenter -t 1 -m mountpoint -q '{mount_path}'"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            mounted = proc.returncode == 0
        except Exception:
            mounted = False
    return {
        "configured": bool(info),
        "mounted": mounted,
        "mount": info,
        "container_path": info.get("container_path"),
        "convert_path": info.get("convert_path"),
    }


def _run_host_mount(cmd_body: str, timeout: int = 180) -> None:
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--privileged",
            "--pid=host",
            "-v",
            f"{PLATFORM_ROOT}:{PLATFORM_ROOT}",
            MOUNT_HELPER_IMAGE,
            "bash",
            "-c",
            f"apt-get update -qq && apt-get install -y -qq cifs-utils util-linux >/dev/null && {cmd_body}",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "mount error").strip()
        raise RuntimeError(err)


def mount_smb(
    *,
    server: str,
    share: str,
    username: str = "",
    password: str = "",
    anonymous: bool = False,
    mount_id: str = "default",
) -> dict[str, Any]:
    server = _validate_server(server)
    share = _validate_share(share)
    mount_id = _validate_mount_id(mount_id)
    mount_path = _mount_path(mount_id)
    mount_path.mkdir(parents=True, exist_ok=True)
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

    unc = f"//{server}/{share}"

    if anonymous:
        opts = "guest,uid=0,gid=0,file_mode=0664,dir_mode=0775,vers=3.0"
        creds_file = None
        user_display = "guest"
    else:
        username = username.strip()
        if not username:
            raise ValueError("Укажите логин или включите анонимный доступ")
        creds_file = _creds_path(mount_id)
        creds_file.write_text(
            f"username={username}\npassword={password}\n",
            encoding="utf-8",
        )
        creds_file.chmod(0o600)
        opts = f"credentials={creds_file},uid=0,gid=0,file_mode=0664,dir_mode=0775,vers=3.0"
        user_display = username

    # Размонтировать прежнюю точку, если занята
    _run_host_mount(
        f"nsenter -t 1 -m bash -c 'mountpoint -q \"{mount_path}\" && umount \"{mount_path}\" || true'"
    )

    _run_host_mount(
        f"nsenter -t 1 -m mount -t cifs '{unc}' '{mount_path}' -o {opts}"
    )

    convert_path = f"/data/smb/{mount_id}"
    host_path = str(mount_path)
    info = {
        "mount_id": mount_id,
        "server": server,
        "share": share,
        "anonymous": anonymous,
        "username": user_display,
        "mount_path": host_path,
        "container_path": f"/opt/road-pdf-platform/mnt/smb/{mount_id}",
        "convert_path": convert_path,
        "unc": unc,
    }
    state = _load_state()
    state["smb_mount"] = info
    _save_state(state)
    return {"ok": True, "mounted": True, "mount": info}


def remount_from_state() -> dict[str, Any] | None:
    """Переподключить SMB после перезапуска портала (пароль из secrets)."""
    state = _load_state()
    info = state.get("smb_mount") or {}
    if not info.get("server") or not info.get("share"):
        return None
    mount_id = info.get("mount_id", "default")
    anonymous = bool(info.get("anonymous"))
    username = ""
    password = ""
    if not anonymous:
        creds = _creds_path(mount_id)
        if not creds.exists():
            return {"ok": False, "error": "Нет сохранённых учётных данных SMB"}
        for line in creds.read_text(encoding="utf-8").splitlines():
            if line.startswith("username="):
                username = line.split("=", 1)[1]
            elif line.startswith("password="):
                password = line.split("=", 1)[1]
    try:
        return mount_smb(
            server=info["server"],
            share=info["share"],
            username=username,
            password=password,
            anonymous=anonymous,
            mount_id=mount_id,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


def unmount_smb() -> dict[str, Any]:
    state = _load_state()
    info = state.get("smb_mount") or {}
    mount_path = info.get("mount_path")
    if not mount_path:
        return {"ok": True, "mounted": False, "message": "SMB не настроен"}

    _run_host_mount(
        f"nsenter -t 1 -m bash -c 'mountpoint -q \"{mount_path}\" && umount \"{mount_path}\" || true'"
    )
    state.pop("smb_mount", None)
    _save_state(state)
    mount_id = info.get("mount_id", "default")
    creds = _creds_path(mount_id)
    if creds.exists():
        creds.unlink()
    return {"ok": True, "mounted": False}
