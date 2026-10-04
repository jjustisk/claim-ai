# CI/CD pipeline

Workflow: [`.github/workflows/ci-cd.yml`](workflows/ci-cd.yml)

```
PUSH → INSTALL → LINT → TEST → BUILD → SCAN → IMAGE → STAGING → APPROVE → PROD
         GitHub                              Docker Hub              Azure ACA
```

| Stage | What it does |
|-------|----------------|
| **INSTALL** | `npm ci` + Python tooling |
| **LINT** | ESLint (frontend), Ruff (backend) |
| **TEST** | PII unit tests + frontend module smoke |
| **BUILD** | `vite build` + Python `compileall` |
| **SCAN** | Trivy fs scan (`aquasecurity/trivy-action@v0.36.0`); reports CRITICAL/HIGH, fails on fixable CRITICAL |
| **IMAGE** | Build/push images to Docker Hub; **backend is skipped (retag only)** when Dockerfile/deps/copied sources are unchanged |
| **STAGING** | Deploy to Azure Container Apps (`staging` environment) |
| **APPROVE** | Manual gate (`production` environment reviewers) |
| **PROD** | Retag images as `*-prod` and deploy |

PRs run through **SCAN** only (no Docker push / Azure deploy).  
Push to `master`/`main` (or `workflow_dispatch`) runs the full CD path.

## One-time GitHub setup

### 1. Secrets (Settings → Secrets and variables → Actions)

| Secret | How to create |
|--------|----------------|
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub → Account Settings → Security → New Access Token (Read & Write) |
| `AZURE_CREDENTIALS` | See below |

```bash
az ad sp create-for-rbac \
  --name "claim-ai-gha" \
  --role contributor \
  --scopes "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/claim-ai-rg" \
  --sdk-auth
```

Paste the entire JSON output into `AZURE_CREDENTIALS`.

Also grant the SP rights to pull/update Container Apps (Contributor on the RG is enough).

### 2. Environments (Settings → Environments)

1. Create **`staging`** (no reviewers required).
2. Create **`production`**.
3. On **production**, enable **Required reviewers** and add yourself/team.  
   That is the **APPROVE** stage in the diagram.

### 3. Optional variables

| Variable | Default |
|----------|---------|
| `DOCKERHUB_NAMESPACE` | `ctinashe` |
| `AZURE_RESOURCE_GROUP` | `claim-ai-rg` |
| `ACA_STAGING_FRONTEND` | `claim-ai-app` |
| `ACA_STAGING_BACKEND` | `backend` |
| `ACA_STAGING_CHROMA` | `chroma` |
| `ACA_PROD_FRONTEND` | `claim-ai-app` |
| `ACA_PROD_BACKEND` | `backend` |
| `ACA_PROD_CHROMA` | `chroma` |

When you split staging/prod apps later, point the `ACA_PROD_*` variables at the production Container App names.

## Image tags on Docker Hub

| Tag pattern | When |
|-------------|------|
| `frontend-staging-<sha7>` / `frontend-staging` | After IMAGE |
| `backend-staging-<sha7>` / `backend-staging` | After IMAGE |
| `chroma-staging-<sha7>` / `chroma-staging` | After IMAGE |
| `*-prod-<sha7>` / `*-prod` | After APPROVE → PROD |
