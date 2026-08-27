# Claim AI — Backend

JSON API for the Vue frontend, plus a temporary HTML test UI under `/ui`.

When Vue is ready, delete `app/pages/` and its `include_router` lines in `main.py`.
Do not put new product behaviour only in pages — add it to `app/api` and `app/services`.

## Layout

```
backend/app/
├── api/          # JSON contract Vue will call (/api/...)
├── pages/        # Throwaway test UI (/ui) — delete when Vue exists
├── services/     # App logic
├── connectors/   # External services
├── config.py
└── main.py
```

Request flow: **Vue or test UI → /api route → service → connector**.

## Local setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

- http://localhost:8000/ui — test UI (claimant + assessor)
- http://localhost:8000/docs — OpenAPI (this is what Vue should follow)
- http://localhost:8000/api/health — API liveness
- http://localhost:8000/ui/storage — blob storage test UI
- http://localhost:8000/ui/pds-search — retrieval endpoint test

CORS already allows the Vite defaults (`http://localhost:5173`). Override with `CORS_ORIGINS` in `.env` if needed.
