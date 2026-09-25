# PII Reduction Service

Secure **Steps 1–3** PII protection for insurance claims:

1. **Input ingestion** — claim records, images, documents (session-scoped)
2. **PII detection & redaction** — Presidio + Australian recognisers, ExifTool metadata stripping, EgoBlur-compatible face/plate redaction, OCR
3. **Secure processing** — validation, sanitised package, LLM-ready payload, encrypted placeholder mapping, authorised rehydration

**No LLM is loaded, called, or required.** Output stops at `READY_FOR_LLM`.

## Temporary test UI

A simple browser UI lives in the repo-root [`ui/`](../ui/) folder:

- **Input** (`/ui/input.html`) — create session, upload claim + files, run sanitize → validate → prepare
- **Output** (`/ui/output.html`) — inspect session status, LLM-ready payload, optional rehydration

With the API running:

```bash
uvicorn app.main:app --reload --port 8000
```

Open [http://127.0.0.1:8000/ui/input.html](http://127.0.0.1:8000/ui/input.html) (or `/` which redirects there).

Default keys match `.env.example` (`dev-processor-key` / `dev-rehydrator-key`).

## Quick start

```bash
cd pii_reduction
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
# Prefer CPU torch wheels on Windows if the default CUDA build is awkward:
#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m spacy download en_core_web_sm
python scripts/download_egoblur_models.py
```

Optional system tools (recommended in production):

- **ExifTool** — primary EXIF/GPS stripper (`METADATA_BACKEND=exiftool`)
- **MAT2** — alternative metadata backend (`METADATA_BACKEND=mat2`)
- **Tesseract** — OCR (`OCR_BACKEND=tesseract`)
- **EgoBlur** — Gen1 JIT models in `models/` (default; OpenCV fallback if missing). Gen2 Aria weights are email-gated at https://www.projectaria.com/tools/egoblur — drop into `models/` if you have them.

```bash
# Set a Fernet key (do not hard-code in source)
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
set CLAIM_AI_ENCRYPTION_KEY=<your-key>   # Windows
export CLAIM_AI_ENCRYPTION_KEY=<your-key> # Unix

uvicorn app.main:app --reload --port 8000
```

## API (auth headers required)

| Endpoint | Method | Roles |
|----------|--------|-------|
| `/api/v1/claims` | POST | PII_PROCESSOR, CLAIMS_USER, ADMIN |
| `/api/v1/claims/{id}/inputs` | POST | PII_PROCESSOR, CLAIMS_USER, ADMIN |
| `/api/v1/claims/{id}/sanitize` | POST | PII_PROCESSOR, ADMIN |
| `/api/v1/claims/{id}/validate` | POST | PII_PROCESSOR, ADMIN |
| `/api/v1/claims/{id}/prepare` | POST | PII_PROCESSOR, ADMIN |
| `/api/v1/claims/{id}/llm-payload` | GET | PII_PROCESSOR, CLAIMS_USER, ADMIN |
| `/api/v1/claims/{id}/rehydrate` | POST | PII_REHYDRATOR, ADMIN |

Headers:

```http
X-API-Key: dev-processor-key
X-Role: PII_PROCESSOR
```

### Example flow

```bash
curl -X POST http://localhost:8000/api/v1/claims \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR"

curl -X POST http://localhost:8000/api/v1/claims/{SESSION}/inputs \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR" \
  -F 'claim_json={"customer_name":"John Smith","address":"12 Maple Street, Sydney NSW","phone":"0412 123 456","claim_description":"Water damage to kitchen"}' \
  -F "files=@damage.jpg"

curl -X POST http://localhost:8000/api/v1/claims/{SESSION}/sanitize \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR"

curl -X POST http://localhost:8000/api/v1/claims/{SESSION}/validate \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR"

curl -X POST http://localhost:8000/api/v1/claims/{SESSION}/prepare \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR"

curl http://localhost:8000/api/v1/claims/{SESSION}/llm-payload \
  -H "X-API-Key: dev-processor-key" -H "X-Role: PII_PROCESSOR"
```

Rehydration (separate role — mapping never returned on llm-payload):

```bash
curl -X POST http://localhost:8000/api/v1/claims/{SESSION}/rehydrate \
  -H "X-API-Key: dev-rehydrator-key" -H "X-Role: PII_REHYDRATOR" \
  -H "Content-Type: application/json" \
  -d '{"content":"CUSTOMER_1 submitted the claim.","rehydration_policy":"FULL"}'
```

## Storage layout

```text
data/
  raw/              # encrypted originals
  sanitised/        # redacted images, sanitised claim.json, OCR
  secure-mapping/   # encrypted placeholder ↔ PII maps (session-scoped)
  llm-ready/        # sanitised package + payload only (no mapping)
  audit/            # PII-free audit log
  sessions/         # session state machine records
```

## State machine

`RECEIVED → PROCESSING → SANITIZED → VALIDATED → READY_FOR_LLM`

Rehydration: `READY_FOR_LLM → REHYDRATION_REQUESTED → REHYDRATED`

Invalid skips (e.g. `RECEIVED → READY_FOR_LLM`) are rejected.

## Tests

```bash
pytest -q
```

Includes privacy tests that assert the LLM payload never contains raw claimant PII, session isolation, unknown-placeholder warnings, and a **no-LLM-dependency** check.

## Explicit non-goals

This service does **not** implement LLM inference, policy reasoning, claim assessment, decision memos, or customer letters.
