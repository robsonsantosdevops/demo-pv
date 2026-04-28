# syntax=docker/dockerfile:1.6

# -----------------------------------------------------------------------------
# Stage 1 — builder: instala dependências Python em uma venv isolada.
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Layer de deps primeiro — cache amigável para rebuilds quando só o código muda.
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2a — test: venv do builder + dev deps + código + tests, roda pytest.
#
# Uso:
#   docker build -t sb-middleware:test --target test -f deploy/Dockerfile .
#   docker run --rm sb-middleware:test
#
# O CMD faz o pytest falhar o container se algum teste não passar.
# -----------------------------------------------------------------------------
FROM builder AS test

WORKDIR /app

# requirements-dev.txt tem `-r requirements.txt` — precisa do base junto.
COPY requirements.txt requirements-dev.txt ./
RUN /opt/venv/bin/pip install -r requirements-dev.txt

COPY src /app/src
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["pytest", "-v", "--color=yes", "tests/"]

# -----------------------------------------------------------------------------
# Stage 2b — runtime: imagem enxuta, só com venv + código + usuário não-root.
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    HEALTH_PORT=8080

# curl apenas para o HEALTHCHECK (~7 MB). Remova se o healthcheck for externo.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Usuário dedicado (UID/GID 10001) para não rodar como root.
RUN groupadd --system --gid 10001 mw \
 && useradd  --system --uid 10001 --gid mw --home-dir /app --shell /usr/sbin/nologin mw

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY src /app/src

# logs/ existe pro JSON formatter escrever app.log quando o dir estiver presente.
RUN mkdir -p /app/logs && chown -R mw:mw /app

USER mw

EXPOSE 8080

# QUEUE_NAME não tem default — precisa vir do deployment (pedidos|oportunidades).
# Healthcheck bate no endpoint liveness do próprio middleware (health.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent --max-time 4 http://localhost:${HEALTH_PORT}/healthz || exit 1

CMD ["python", "-m", "middleware"]
