#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONTAINER_NAME="${CONTAINER_NAME:-tgmaxrelay}"
SERVICE_NAME="${SERVICE_NAME:-tgmaxrelay}"
IMAGE_NAME="${IMAGE_NAME:-tgmaxrelay}"
NETWORK_NAME="${NETWORK_NAME:-my_projects_my_network}"
DNS_1="${DNS_1:-1.1.1.1}"
DNS_2="${DNS_2:-8.8.8.8}"
TELEGRAM_API_HOST_IP="${TELEGRAM_API_HOST_IP:-149.154.167.220}"

SKIP_PULL="${SKIP_PULL:-0}"
FORCE_DOCKER_RUN="${FORCE_DOCKER_RUN:-0}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/../docker-compose.yml}"

if [[ ! -f ".env" ]]; then
  echo "[deploy] .env not found in $ROOT_DIR" >&2
  exit 1
fi

USE_COMPOSE=0
if [[ "$FORCE_DOCKER_RUN" != "1" ]] && [[ -f "$COMPOSE_FILE" ]] \
  && grep -qE '^[[:space:]]+'"${SERVICE_NAME}"':' "$COMPOSE_FILE"; then
  USE_COMPOSE=1
fi

echo "[deploy] root: $ROOT_DIR"
echo "[deploy] container/service: $CONTAINER_NAME"
if [[ "$USE_COMPOSE" == "1" ]]; then
  echo "[deploy] mode: docker compose"
  echo "[deploy] compose file: $COMPOSE_FILE"
else
  echo "[deploy] mode: docker run"
  echo "[deploy] image: $IMAGE_NAME"
  echo "[deploy] network: $NETWORK_NAME"
fi
if [[ "$SKIP_PULL" != "1" ]]; then
  echo "[deploy] git pull ($ROOT_DIR)"
  git pull --ff-only
else
  echo "[deploy] skip git pull (SKIP_PULL=1)"
fi

if [[ "$USE_COMPOSE" == "1" ]]; then
  COMPOSE_DIR="$(cd "$(dirname "$COMPOSE_FILE")" && pwd)"
  COMPOSE_BASENAME="$(basename "$COMPOSE_FILE")"
  (
    cd "$COMPOSE_DIR"
    docker compose -f "$COMPOSE_BASENAME" build "$SERVICE_NAME"
    docker compose -f "$COMPOSE_BASENAME" up -d "$SERVICE_NAME"
  )
else
  echo "[deploy] stopping old container (if exists)"
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true

  echo "[deploy] building image"
  docker build -t "$IMAGE_NAME" .

  echo "[deploy] starting container"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network "$NETWORK_NAME" \
    --add-host "host.docker.internal:host-gateway" \
    --env-file .env \
    --dns "$DNS_1" \
    --dns "$DNS_2" \
    --add-host "api.telegram.org:$TELEGRAM_API_HOST_IP" \
    "$IMAGE_NAME"
fi

echo "[deploy] container status:"
docker ps --filter "name=^/${CONTAINER_NAME}$" --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}"

echo "[deploy] Telegram getMe"
docker exec "$CONTAINER_NAME" python - <<'PY'
import json
import os
import sys

import requests

token = os.getenv("API_TOKEN")
if not token:
    print("[deploy] ERROR: API_TOKEN missing")
    sys.exit(1)

url = f"https://api.telegram.org/bot{token}/getMe"
resp = requests.get(url, timeout=15)
print(f"[deploy] getMe status={resp.status_code}")
if resp.status_code != 200:
    print(resp.text[:500])
    sys.exit(1)
data = resp.json()
print("[deploy] bot:", data.get("result", {}).get("username"))
PY

echo "[deploy] done"
