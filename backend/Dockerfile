# syntax=docker/dockerfile:1
# Thin "code ship" image — Python deps install at container start (not baked into Hub layers).
# Why: baking pip install (spaCy, Chroma/ONNX, OpenCV, …) made a ~3.5GB layer that
# timed out on Docker Hub free-tier uploads. Code + apt runtime libs stay small.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    CLAIM_AI_DEPS_DIR=/deps \
    PATH=/deps/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/app \
    PYTHONUSERBASE=/deps

# No gcc/g++ — use prebuilt wheels only so the Hub image stays small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    exiftool \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY app ./app
COPY pii_reduction ./pii_reduction
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh

RUN sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/chroma /app/pii_reduction/data /deps

EXPOSE 8000

# First boot installs deps (can take several minutes); later boots are fast via /deps volume
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=8 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
# Only trust X-Forwarded-* from private Docker/K8s networks (not the public internet).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1"]
