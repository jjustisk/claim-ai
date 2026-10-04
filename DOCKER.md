# Claim AI — Docker deployment

## Secrets: Azure Key Vault (default)

The backend loads `DATABASE_URL`, `JWT_SECRET_KEY`, storage, Foundry, ACS, etc.
from **Key Vault** (`claim-ai-kv`) — same path as running outside Docker.

`.env.docker` is **not** a secrets dump. It only holds:

- ports / CORS / feature toggles
- vault name
- Azure identity so the container can *read* the vault
- optional `CLAIM_AI_ENCRYPTION_KEY` if that value is not in the vault yet
- **`CHROMA_AUTH_TOKEN`** (required) — Bearer token shared by the Chroma server and backend

Nothing secret is baked into the image (see `.dockerignore`).

## Architecture

| Service | Image | Network exposure |
|---------|--------|------------------|
| `chroma` | `ctinashe/claim-ai-chroma:<tag>` (chromadb==0.6.3) | **Internal only** (no host ports). Token auth required. |
| `backend` | `ctinashe/claim-ai-backend:<tag>` | Host `BACKEND_PORT` (default 8000) |
| `frontend` | `ctinashe/claim-ai-frontend:<tag>` | Host `FRONTEND_PORT` (default 8080) |
| `postgres` | `postgres:16-alpine` | Profile `local-db` only; bound to `127.0.0.1` |

Backend connects to Chroma as `http://chroma:8000` with `Authorization: Bearer <CHROMA_AUTH_TOKEN>`.

## One-time setup

```bash
cd claim-ai
cp .env.docker.example .env.docker
```

Generate a Chroma token and put it in `.env.docker`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Auth to Key Vault from Docker

| Where the container runs | What to set in `.env.docker` |
|--------------------------|------------------------------|
| Azure Container Apps / AKS | Leave SP blank → **Managed Identity** (grant it Key Vault Secrets User) |
| Local Docker Desktop | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (SP with vault get) |

Also set `CORS_ORIGINS` to your frontend origin (must match `FRONTEND_PORT`).

## Run against Azure resources (normal path)

Sync secrets from Key Vault (needs `az login`), then start **without** local-db:

```powershell
.\scripts\sync-env-from-vault.ps1
docker compose --env-file .env.docker -f docker-compose.hub.yml up -d
```

Open **http://127.0.0.1:8088** (use `127.0.0.1`, not `localhost`, on Windows/WSL).

This uses Azure Postgres, Blob, Foundry, ACS from the vault. Chroma stays the compose service.

## Optional local Postgres

Only if you intentionally skip Azure DB:

```bash
docker compose --env-file .env.docker --profile local-db up --build
```

Escape hatch only — empty local DB, not your Azure users.

## Security defaults

- Sync secrets from Key Vault (`sync-env-from-vault.ps1`); never bake secrets into images
- Weak `jwt-secret-key` values are **auto-rotated** in Key Vault
- `APP_ENV=production` → `/docs` and `/ui` test pages off
- Login rate limits (API + nginx), timing-safe failed logins, email normalized
- Production requires Postgres `sslmode=require` for non-local hosts
- Trusted hosts + hardened security headers / CSP on API and nginx
- Backend/frontend/Chroma publish only on `127.0.0.1`; Chroma has no host ports
- `no-new-privileges` on compose services; uvicorn trusts `X-Forwarded-*` only from private nets
- `.dockerignore` keeps `.env*`, PII data, and keys out of the image

## Why backend was ~3.5GB (and timed out on Hub)

The old Dockerfile ran `pip install -r requirements.txt` **at image build time**.
That baked spaCy (`en_core_web_lg`), Chroma/ONNX, OpenCV, etc. into one huge layer.

**New plan:** ship a thin **code-only** backend image. On first container start the
entrypoint installs Python deps into `/deps` (cached until `requirements.txt` changes):

- **Local Compose:** `python_deps` named volume
- **Azure ACA:** Azure Files share `python-deps` mounted at `/deps` (see `scripts/mount-backend-python-deps.ps1`)

Code-only deploys reuse that volume — they do **not** reinstall spaCy/OpenCV/etc.

## Private Docker Hub deploy (recommended)

One private repo (Hub free-plan limit), three tags:

| Tag | Contents |
|-----|----------|
| `ctinashe/claim-ai:backend-local` | App code + apt libs (thin; pip at runtime) |
| `ctinashe/claim-ai:frontend-local` | Built Vue + nginx |
| `ctinashe/claim-ai:chroma-local` | Chroma 0.6.3 server |

```powershell
# Build thin images → push private Hub → pull → run until healthy
.\scripts\deploy-dockerhub.ps1
```

Pull-only later:

```powershell
docker compose --env-file .env.docker -f docker-compose.hub.yml --profile local-db pull
docker compose --env-file .env.docker -f docker-compose.hub.yml --profile local-db up -d
```

## Useful commands

```bash
docker compose --env-file .env.docker --profile local-db up --build -d
docker compose --env-file .env.docker --profile local-db ps
docker compose --env-file .env.docker --profile local-db logs -f backend chroma
docker compose --env-file .env.docker --profile local-db down
```

## Health

- http://localhost:8000/health
- http://localhost:8080/ (or your `FRONTEND_PORT`)
- Chroma: only from inside the network (`chroma:8000`); heartbeat is auth-exempt for probes
