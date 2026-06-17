#!/usr/bin/env bash
# Установка road-pdf-platform на новом клиенте (только Docker Hub, без исходников).
set -euo pipefail

ROOT="${PLATFORM_ROOT:-/opt/road-pdf-platform}"
PORT="${PORTAL_PORT:-80}"
COMPOSE_FILE="${PLATFORM_COMPOSE_FILE:-docker-compose.client.yml}"
PORTAL_IMAGE="${PORTAL_IMAGE:-makeden/portal:latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Ошибка: Docker не установлен." >&2
  exit 1
fi

mkdir -p "$ROOT"

echo "→ pull $PORTAL_IMAGE"
docker pull "$PORTAL_IMAGE"

echo "→ bootstrap compose в $ROOT"
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /usr/bin/docker:/usr/local/bin/docker:ro \
  -v "$ROOT:$ROOT" \
  -e PLATFORM_INSTALL_ROOT="$ROOT" \
  -e PLATFORM_COMPOSE_FILE="$ROOT/$COMPOSE_FILE" \
  -e DOCKER_COMPOSE_BIN=/usr/local/bin/docker-compose \
  "$PORTAL_IMAGE" \
  python -m portal.compose_cli bootstrap \
    --root "$ROOT" \
    --compose-file "$COMPOSE_FILE" \
    --portal-port "$PORT" \
    --force \
    --pull \
    --up

if docker ps --format '{{.Names}}' | grep -qx masha-print; then
  echo "→ подключение masha-print к сети road-platform"
  docker network connect road-platform masha-print 2>/dev/null || true
fi

echo ""
echo "Готово."
echo "  Портал:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}/"
echo "  Сервисы: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}/services"
