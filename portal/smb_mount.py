"""Подключение SMB/CIFS: учётные данные + проверка через smbclient (без kernel CIFS)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from portal.platform_control import PLATFORM_ROOT, _load_state, _save_state

SECRETS_DIR = PLATFORM_ROOT / "secrets" / "smb"
MNT_ROOT = PLATFORM_ROOT / "mnt" / "smb"
MOUNT_HELPER_IMAGE = "debian:bookworm-slim"
CONVERT_CONTAINER = "convert-to-pdf-service"

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def _docker_bin() -> str:
    for candidate in (
        os.getenv("DOCKER_BIN"),
        shutil.which("docker"),
        "/usr/local/bin/docker",
        "/usr/bin/docker",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("Docker CLI не найден в контейнере портала")


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


def _parse_username(username: str, domain: str = "") -> tuple[str, str]:
    username = username.strip()
    domain = domain.strip()
    if "\\" in username:
        domain, username = username.split("\\", 1)
    elif "/" in username:
        domain, username = username.split("/", 1)
    return domain.strip(), username.strip()


def _format_mount_error(err: str) -> str:
    low = err.lower()
    if "access denied" in low or "status_access_denied" in low or "return code = -13" in low:
        return (
            "Windows отклонил вход (ACCESS_DENIED). Проверьте логин/пароль, "
            "доступ к шаре для пользователя и NTFS-права на папку."
        )
    if "read-only" in low:
        return (
            "Не удалось подключиться к шаре (часто из-за отказа в доступе). "
            "Проверьте права пользователя на шару и папку."
        )
    return err


def _cleanup_stale_cifs(mount_path: str) -> None:
    """Убрать старые kernel CIFS, если остались от прежних версий."""
    if not mount_path:
        return
    try:
        subprocess.run(
            [
                _docker_bin(),
                "run",
                "--rm",
                "--privileged",
                "--pid=host",
                MOUNT_HELPER_IMAGE,
                "bash",
                "-c",
                f"apt-get update -qq && apt-get install -y -qq util-linux >/dev/null && "
                f"nsenter -t 1 -m bash -c 'umount -l -f \"{mount_path}\" 2>/dev/null || true; "
                f"umount -l -f \"{mount_path}\" 2>/dev/null || true'",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        pass


def _test_smbclient(unc: str, creds_file: Path) -> None:
    """Проверка доступа к шаре через smbclient в контейнере convert."""
    proc = subprocess.run(
        [
            _docker_bin(),
            "exec",
            CONVERT_CONTAINER,
            "smbclient",
            unc,
            "-A",
            str(creds_file),
            "-c",
            "ls",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "smbclient error").strip()
        raise RuntimeError(_format_mount_error(err))


def _smb_accessible() -> bool:
    state = _load_state()
    info = state.get("smb_mount") or {}
    unc = info.get("unc")
    mount_id = info.get("mount_id", "default")
    creds = _creds_path(mount_id)
    if not unc or not creds.exists():
        return False
    try:
        _test_smbclient(unc, creds)
        return True
    except Exception:
        return False


def smb_status() -> dict[str, Any]:
    state = _load_state()
    info = state.get("smb_mount") or {}
    mounted = _smb_accessible() if info else False
    state["smb_mounted"] = mounted
    _save_state(state)
    return {
        "configured": bool(info),
        "mounted": mounted,
        "mount": info,
        "container_path": info.get("container_path"),
        "convert_path": info.get("convert_path"),
    }


def mount_smb(
    *,
    server: str,
    share: str,
    username: str = "",
    password: str = "",
    domain: str = "",
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
    domain = domain.strip()
    user_display = "guest"

    if anonymous:
        raise ValueError("Анонимный доступ не поддерживается в этой конфигурации — укажите логин")
    username = username.strip()
    if not username:
        raise ValueError("Укажите логин")
    domain, user = _parse_username(username, domain)
    creds_file = _creds_path(mount_id)
    lines = [f"username={user}", f"password={password}"]
    if domain:
        lines.append(f"domain={domain}")
    creds_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    creds_file.chmod(0o600)
    user_display = f"{domain}\\{user}" if domain else user

    _cleanup_stale_cifs(str(mount_path))
    _test_smbclient(unc, creds_file)

    convert_path = f"/data/smb/{mount_id}"
    host_path = str(mount_path)
    info = {
        "mount_id": mount_id,
        "server": server,
        "share": share,
        "anonymous": anonymous,
        "username": user_display,
        "domain": domain,
        "mount_path": host_path,
        "container_path": f"/opt/road-pdf-platform/mnt/smb/{mount_id}",
        "convert_path": convert_path,
        "unc": unc,
    }
    state = _load_state()
    state["smb_mount"] = info
    state["smb_mounted"] = True
    _save_state(state)
    return {"ok": True, "mounted": True, "mount": info}


def remount_from_state() -> dict[str, Any] | None:
    """Переподключить SMB после перезапуска портала (пароль из secrets)."""
    state = _load_state()
    info = state.get("smb_mount") or {}
    if not info.get("server") or not info.get("share"):
        return None
    mount_id = info.get("mount_id", "default")
    creds = _creds_path(mount_id)
    if not creds.exists():
        return {"ok": False, "error": "Нет сохранённых учётных данных SMB"}
    unc = info.get("unc") or f"//{info['server']}/{info['share']}"
    try:
        _cleanup_stale_cifs(info.get("mount_path", ""))
        _test_smbclient(unc, creds)
        state["smb_mounted"] = True
        _save_state(state)
        return {"ok": True, "mounted": True, "mount": info}
    except Exception as e:
        state["smb_mounted"] = False
        _save_state(state)
        return {"ok": False, "error": str(e)}


def unmount_smb() -> dict[str, Any]:
    state = _load_state()
    info = state.get("smb_mount") or {}
    mount_path = info.get("mount_path")
    if mount_path:
        _cleanup_stale_cifs(mount_path)
    state.pop("smb_mount", None)
    state["smb_mounted"] = False
    _save_state(state)
    mount_id = info.get("mount_id", "default")
    creds = _creds_path(mount_id)
    if creds.exists():
        creds.unlink()
    return {"ok": True, "mounted": False}
