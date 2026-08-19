# External Service Connections

Each outside service (database, file storage, etc.) has its own file in `app/connectors/`. The rest of the app should use those files instead of setting up connections on its own.

```
api/ and services/
      |
      +-- app/connectors/storage.py --------> Azure Blob Storage
      |
      +-- app/connectors/db.py -------------> PostgreSQL
      |
      +-- app/connectors/chromadb_store.py -> ChromaDB
      |
      +-- app/connectors/foundry.py --------> Azure AI Foundry (GPT 5.5, Claude via model-router)
      |
      +-- app/connectors/secrets.py --------> Azure Key Vault
```

Connection details (passwords, URLs, keys) are loaded in `app/config.py`, which gets them from `app/connectors/secrets.py`. The connection files read from `settings` — they do not talk to Key Vault directly.

---

## `app/connectors/secrets.py` — Azure Key Vault

**What it connects to:** Azure Key Vault (`claim-ai-kv`)

**What belongs here:**
- Logging in to Azure (managed identity when deployed, Azure CLI when running locally)
- Creating and reusing the Key Vault client
- Fetching secrets with `get_keyvault_secret(name)`
- A separate client for admin scripts that seed secrets (`create_provisioning_secret_client`)
- Mappings between secret names and settings fields (`VAULT_SECRET_FIELDS`, `ENV_VAULT_SECRETS`)

**What does not belong here:**
- The settings model itself (that lives in `config.py`)
- Setting up blob storage, the database, or ChromaDB
- App logic that uses secret values

**How to use it:**
```python
from app.connectors.secrets import get_keyvault_secret

value = get_keyvault_secret("database-url")
```

In normal app code, use `from app.config import settings` to read values. Only import from `secrets.py` when you need vault details or admin/provisioning helpers.

---

## `app/connectors/db.py` — PostgreSQL

**What it connects to:** PostgreSQL (Azure PostgreSQL in production)

**What belongs here:**
- The async database engine and session setup
- `Base` — the shared starting point for table models
- `get_db()` — gives each API request its own database session
- `get_sync_connection()` — a plain connection for scripts and one-off migrations

**What does not belong here:**
- Table/model definitions (those go in `api/schemas/`)
- Queries or route handlers
- Loading passwords or connection strings from Key Vault

**How to use it:**
```python
from app.connectors.db import get_db, Base, engine, get_sync_connection
```

---

## `app/connectors/storage.py` — Azure Blob Storage

**What it connects to:** Azure Blob Storage (file storage in Azure)

**What belongs here:**
- One shared blob storage client for the whole app
- Helpers to get container clients (`get_images_container_client`, etc.)
- Upload, download, delete, and list helpers for the configured containers
- Shutting down the client on app exit (`close_blob_service_client()`)

**What does not belong here:**
- Claim submission or other app-specific rules
- Using the storage connection string outside this file
- Creating a blob client directly anywhere else in the codebase

**How to use it:**
```python
from app.connectors.storage import upload_image, get_blob_service_client, close_blob_service_client

await upload_image("path/to/blob", data, content_type="image/jpeg")
```

---

## `app/connectors/chromadb_store.py` — ChromaDB

**What it connects to:** ChromaDB (either a running server or local storage on disk)

**What belongs here:**
- One shared ChromaDB client (remote server or local folder)
- Getting a collection with `get_collection(name)`
- Resetting the client in tests with `reset_chroma_client()`

**What does not belong here:**
- Building embeddings or search logic for claims
- Workflow code that ties vector search to business rules
- ChromaDB host, port, or folder settings (those go in `config.py` / `.env`)

**How to use it:**
```python
from app.connectors.chromadb_store import get_chroma_client, get_collection

collection = get_collection()
```

---

## `app/connectors/foundry.py` — Azure AI Foundry

**What it connects to:** Azure AI Foundry — both language models used by the app live here.

| Model | Model ID | How it is accessed |
| --- | --- | --- |
| GPT 5.5 | `gpt-5.5` | Direct deployment (OpenAI-compatible Responses API) |
| Claude Opus | `claude-opus-4-8` | **model-router** deployment in australiaeast (quality mode) |

Both models are served from your Azure AI Foundry project. The app does not call openai.com or anthropic.com directly, and does not use OpenAI or Anthropic API keys.

In **australiaeast**, Claude Opus cannot be deployed directly (regional SKU limit). The Claude slot uses the **model-router** deployment instead. Router picks the best model available in-region — GPT models today, Claude Opus when you can deploy it. Deploy Claude in Foundry and add it to the router subset to route to real Opus.

**What belongs here:**
- Logging in to Foundry using Azure credentials (managed identity or Azure CLI)
- One shared Foundry project client
- Client for GPT 5.5 (`get_gpt_client()`)
- Claude via model-router (`create_claude_response()`, `uses_claude_router()`)
- Direct Anthropic client for regions with a Claude deployment (`get_claude_client()`)
- Deployment name helpers (`get_gpt_deployment()`, `get_claude_deployment()`, `get_router_deployment()`)
- Resetting cached clients in tests (`reset_foundry_clients()`)

**What does not belong here:**
- Claim review, fraud detection, or other app logic
- Prompt templates or agent workflows
- OpenAI or Anthropic API keys (not used — Foundry handles auth via Azure)
- Creating model clients anywhere else in the codebase

**How to use it:**
```python
from app.connectors.foundry import (
    get_gpt_client,
    get_gpt_deployment,
    create_claude_response,
    uses_claude_router,
)

gpt = get_gpt_client()
response = gpt.responses.create(
    model=get_gpt_deployment(),
    input="Summarize this claim...",
)

# Claude Opus slot — routes through model-router in australiaeast
claude_response = create_claude_response("Review this claim...")
print(claude_response.output_text)
print(claude_response.model)  # underlying model the router picked
```

**Settings (in `.env` or Key Vault):**
- `AZURE_AI_PROJECT_ENDPOINT` — required; your Foundry project URL
- `AZURE_AI_SERVICES_ENDPOINT` — optional; derived from the project endpoint if omitted
- `FOUNDRY_GPT_DEPLOYMENT` — GPT 5.5 deployment name (default: `gpt-5.5`)
- `FOUNDRY_ROUTER_DEPLOYMENT` — model-router deployment name (default: `model-router`)
- `FOUNDRY_CLAUDE_DEPLOYMENT` — Claude path deployment (default: `model-router`)

---

## `app/config.py` — Settings (not a connection file)

**What it does:** Loads all settings from Key Vault (through `app/connectors/secrets.py`) and environment variables, then exposes them as `settings`.

Connection files read from `settings`. Routes and services import from the connection files.

---

## Rules for new code

- One outside service = one connection file in `app/connectors/`.
- All LLM calls go through `foundry.py` — GPT 5.5 direct, Claude Opus via model-router in australiaeast.
- Do not create Azure clients in routers, services, or scripts — import from the right connection file instead.
- Do not read from Key Vault anywhere except `secrets.py`.
- Adding a new outside service? Create a new dedicated connection file in `app/connectors/` using the same pattern.
