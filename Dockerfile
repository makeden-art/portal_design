# Сборка из корня road-pdf-platform:
#   docker compose -f docker-compose.platform.yml build portal
FROM python:3.11-slim

WORKDIR /app

COPY lisp_Nikolay/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb xauth \
    libxcb-util1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
    libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
    libfontconfig1 libfreetype6 libgl1 libglib2.0-0 \
    libreoffice-writer-nogui libreoffice-calc-nogui \
    docker.io curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG COMPOSE_VERSION=2.27.0
RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in amd64) ARCH=x86_64 ;; arm64) ARCH=aarch64 ;; esac && \
    curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${ARCH}" \
      -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose

RUN ln -s /usr/lib/x86_64-linux-gnu/libxcb-util.so.1 /usr/lib/x86_64-linux-gnu/libxcb-util.so.0 || true

COPY lisp_Nikolay/ODAFileConverter*.deb /tmp/oda.deb
RUN dpkg -i /tmp/oda.deb || apt-get install -f -y && rm /tmp/oda.deb

# Ядро портала
COPY portal_design/portal ./portal
COPY portal_design/static ./static
COPY portal_design/ui ./ui
COPY portal_design/VERSION ./VERSION
COPY portal_design/main.py ./main.py

# Модуль lisp_Nikolay (утилиты)
COPY lisp_Nikolay/portal_utilities ./portal_utilities
COPY lisp_Nikolay/vol_multi_dxf.py lisp_Nikolay/normocontrol.py lisp_Nikolay/normocontrol_engine.py \
     lisp_Nikolay/crypto_stamp.py lisp_Nikolay/dwg_converter.py lisp_Nikolay/office_checkers.py \
     lisp_Nikolay/pdf_jobs.py ./
COPY lisp_Nikolay/pipeline ./pipeline

ENV PYTHONUNBUFFERED=1
ENV PORTAL_PLUGINS=portal_utilities

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
