# Claim AI — Backend

FastAPI service.

## Local setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env      # if not already done at repo root
uvicorn app.main:app --reload
```

Then visit:
- http://localhost:8000/health — liveness check
- http://localhost:8000/docs — OpenAPI docs

## Next additions (Phase 0)

- `app/core/config.py` — settings loaded from `.env`
- `app/db/` — SQLAlchemy engine/session + Alembic migrations matching the ER diagram in `docs/`
- `app/api/auth.py` — JWT auth with claimant/assessor role claims
