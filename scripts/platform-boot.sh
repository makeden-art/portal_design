#!/usr/bin/env bash
# Автозапуск road-pdf-platform после перезагрузки хоста (systemd).
set -euo pipefail

ROOT="${PLATFORM_INSTALL_ROOT:-/opt/road-pdf-platform}"
COMPOSE_FILE="${PLATFORM_COMPOSE_FILE:-$ROOT/docker-compose.client.yml}"
PORTAL_IMAGE="${PORTAL_IMAGE:-makeden/portal:latest}"
COMPOSE_BIN="${DOCKER_COMPOSE_BIN:-docker-compose}"

log() { echo "[road-platform] $*"; }

if ! command -v docker >/dev/null 2>&1; then
  log "Docker не найден"
  exit 1
fi

for _ in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker info >/dev/null 2>&1; then
  log "Docker daemon недоступен"
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  log "Compose-файл не найден: $COMPOSE_FILE"
  exit 1
fi

log "Запуск сервисов из $COMPOSE_FILE"

run_boot() {
  if [[ -d "$ROOT/portal_design/portal" ]] && command -v python3 >/dev/null 2>&1; then
    PLATFORM_INSTALL_ROOT="$ROOT" \
    PLATFORM_COMPOSE_FILE="$COMPOSE_FILE" \
    DOCKER_COMPOSE_BIN="$COMPOSE_BIN" \
    PYTHONPATH="$ROOT/portal_design" \
    python3 -c "from portal.platform_control import ensure_platform_running; import json, sys; r=ensure_platform_running(); print(json.dumps(r, ensure_ascii=False)); sys.exit(0 if r.get('ok') else 1)"
    return
  fi
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /usr/bin/docker:/usr/local/bin/docker:ro \
    -v "$ROOT:$ROOT" \
    -e PLATFORM_INSTALL_ROOT="$ROOT" \
    -e PLATFORM_COMPOSE_FILE="$COMPOSE_FILE" \
    -e DOCKER_COMPOSE_BIN="$COMPOSE_BIN" \
    "$PORTAL_IMAGE" \
    python -c "from portal.platform_control import ensure_platform_running; import json, sys; r=ensure_platform_running(); print(json.dumps(r, ensure_ascii=False)); sys.exit(0 if r.get('ok') else 1)"
}

run_boot

log "Готово"
