#!/bin/sh
# Install Python deps into /deps (volume) on first start or when requirements change.
set -eu

DEPS_DIR="${CLAIM_AI_DEPS_DIR:-/deps}"
MARKER="${DEPS_DIR}/.requirements.sha256"
REQ_FILE="/app/requirements.txt"

mkdir -p "$DEPS_DIR" /app/pii_reduction/data /app/data/chroma

export PYTHONUSERBASE="$DEPS_DIR"
export PATH="${DEPS_DIR}/bin:${PATH}"
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"

CURRENT="$(sha256sum "$REQ_FILE" | awk '{print $1}')"
INSTALLED=""
if [ -f "$MARKER" ]; then
  INSTALLED="$(cat "$MARKER")"
fi

if [ "$CURRENT" != "$INSTALLED" ]; then
  echo "[entrypoint] Installing Python dependencies into ${DEPS_DIR} (first boot / requirements changed)..."
  python -m pip install --upgrade pip
  python -m pip install --user -r "$REQ_FILE"
  echo "$CURRENT" > "$MARKER"
  echo "[entrypoint] Dependency install complete."
else
  echo "[entrypoint] Dependencies already installed (cache hit)."
fi

exec "$@"
