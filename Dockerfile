# Ядро портала (без утилит — они в отдельных контейнерах)
FROM python:3.11-slim

WORKDIR /app

COPY portal_design/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG COMPOSE_VERSION=2.27.0
RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in amd64) ARCH=x86_64 ;; arm64) ARCH=aarch64 ;; esac && \
    curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${ARCH}" \
      -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose

COPY portal_design/portal ./portal
COPY portal_design/static ./static
COPY portal_design/ui ./ui
COPY portal_design/VERSION ./VERSION
COPY portal_design/main.py ./main.py

ENV PYTHONUNBUFFERED=1
ENV PORTAL_PLUGINS=portal.hub_modules

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
