"""CLI: генерация compose и первичная установка платформы на клиенте."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from portal.compose_generator import (
    ComposeGenerateOptions,
    compose_output_path,
    generate_compose_yaml,
    write_compose_file,
)
from portal.modules import get_all_modules
from portal.platform_services import DEFAULT_COMPOSE_NAME, DEFAULT_ROOT, DEFAULT_WATCHTOWER_TOKEN


def _compose_bin() -> str:
    return os.getenv("DOCKER_COMPOSE_BIN", "docker-compose")


def _initial_state() -> dict:
    return {
        "disabled_services": [],
        "portal_modules": list(get_all_modules()),
        "smb_mounted": False,
    }


def _ensure_platform_files(opts: ComposeGenerateOptions) -> None:
    opts.root.mkdir(parents=True, exist_ok=True)
    state_path = opts.root / "platform.state.json"
    if not state_path.exists():
        state_path.write_text(
            json.dumps(_initial_state(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    runtime_path = opts.root / "platform.runtime.env"
    if not runtime_path.exists():
        modules = ",".join(get_all_modules())
        runtime_path.write_text(f"PORTAL_MODULES={modules}\n", encoding="utf-8")


def _run_compose(opts: ComposeGenerateOptions, *args: str, timeout: int = 300) -> int:
    compose_file = compose_output_path(opts)
    cmd = [_compose_bin(), "-f", str(compose_file)]
    runtime = opts.root / "platform.runtime.env"
    if runtime.exists():
        cmd.extend(["--env-file", str(runtime)])
    cmd.extend(args)
    proc = subprocess.run(cmd, cwd=str(opts.root), timeout=timeout)
    return proc.returncode


def cmd_write(args: argparse.Namespace) -> int:
    opts = _opts_from_args(args)
    path = compose_output_path(opts)
    if path.exists() and not args.force:
        print(f"Файл уже существует: {path} (используйте --force)", file=sys.stderr)
        return 1
    write_compose_file(opts, force=True)
    print(path)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    opts = _opts_from_args(args)
    sys.stdout.write(generate_compose_yaml(opts))
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    opts = _opts_from_args(args)
    compose_path = compose_output_path(opts)

    if compose_path.exists() and not args.force:
        print(f"Compose уже есть: {compose_path}", file=sys.stderr)
    else:
        write_compose_file(opts, force=True)
        print(f"Записан {compose_path}")

    _ensure_platform_files(opts)

    if args.pull:
        print("docker compose pull …")
        rc = _run_compose(opts, "pull", "portal", "watchtower")
        if rc != 0:
            return rc

    if args.up:
        print("docker compose up -d portal watchtower …")
        rc = _run_compose(opts, "up", "-d", "portal", "watchtower", "--no-build")
        if rc != 0:
            return rc
        print(f"Портал: http://127.0.0.1:{opts.portal_port}/")
        print(f"Сервисы: http://127.0.0.1:{opts.portal_port}/services")

    return 0


def _opts_from_args(args: argparse.Namespace) -> ComposeGenerateOptions:
    root = Path(args.root).resolve()
    compose_file = args.compose_file or DEFAULT_COMPOSE_NAME
    if not compose_file.startswith("/"):
        compose_path = root / compose_file
    else:
        compose_path = Path(compose_file)
    return ComposeGenerateOptions(
        root=root,
        compose_filename=compose_path.name,
        portal_port=args.portal_port,
        watchtower_token=args.watchtower_token,
        external_network=args.external_network,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="portal.compose_cli",
        description="Генерация docker-compose для клиентской установки road-pdf-platform",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=os.getenv("PLATFORM_INSTALL_ROOT", str(DEFAULT_ROOT)),
        help=f"Каталог установки (по умолчанию {DEFAULT_ROOT})",
    )
    common.add_argument(
        "--compose-file",
        default=os.getenv("PLATFORM_COMPOSE_FILE", DEFAULT_COMPOSE_NAME),
        help="Имя или путь compose-файла внутри --root",
    )
    common.add_argument("--portal-port", type=int, default=int(os.getenv("PORTAL_PORT", "80")))
    common.add_argument(
        "--watchtower-token",
        default=os.getenv("WATCHTOWER_TOKEN", DEFAULT_WATCHTOWER_TOKEN),
    )
    common.add_argument(
        "--external-network",
        action="store_true",
        help="Пометить сеть road-platform как external: true",
    )

    sub = p.add_subparsers(dest="command", required=True)

    w = sub.add_parser("write", parents=[common], help="Записать compose-файл на диск")
    w.add_argument("--force", action="store_true", help="Перезаписать существующий файл")
    w.set_defaults(func=cmd_write)

    s = sub.add_parser("show", parents=[common], help="Вывести compose в stdout")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("bootstrap", parents=[common], help="Создать compose, state и опционально запустить ядро")
    b.add_argument("--force", action="store_true", help="Перезаписать compose-файл")
    b.add_argument("--pull", action="store_true", help="docker compose pull portal watchtower")
    b.add_argument("--up", action="store_true", help="docker compose up -d portal watchtower")
    b.set_defaults(func=cmd_bootstrap)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
