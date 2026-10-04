# syntax=docker/dockerfile:1
# Claim AI — ChromaDB HTTP server (pinned to match backend chromadb==0.6.3)
# Runs on the private compose network with token auth. Do not publish ports.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    ANONYMIZED_TELEMETRY=FALSE \
    CHROMA_HOST_ADDR=0.0.0.0 \
    CHROMA_HOST_PORT=8000 \
    CHROMA_SERVER_HTTP_PORT=8000 \
    IS_PERSISTENT=TRUE \
    PERSIST_DIRECTORY=/chroma/chroma

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install "chromadb==0.6.3" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin chromauser \
    && mkdir -p /chroma/chroma \
    && chown -R chromauser:chromauser /chroma

WORKDIR /chroma
USER chromauser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=10 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/heartbeat || exit 1

# Auth is configured via env (CHROMA_SERVER_AUTHN_*); set by compose.
CMD ["chroma", "run", "--host", "0.0.0.0", "--port", "8000", "--path", "/chroma/chroma"]
