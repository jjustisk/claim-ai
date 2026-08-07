from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from app.database import engine, Base
from app.routers import auth as auth_router
from app.dependencies import require_assessor, require_claimant

import app.schema

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan, title="Claim AI API", version="0.0.1")
app.include_router(auth_router.router)
@app.get("/health")
def health() -> dict:
    """Basic liveness check. Extend later to also ping the database."""
    return {"status": "ok"}

@app.get("/test/assessor-only")
def assessor_only_route(user: dict = Depends(require_assessor)):
    return {"message": f"Hello assessor {user['email']}"}

@app.get("/test/claimant-only")
def claimant_only_route(user: dict = Depends(require_claimant)):
    return {"message": f"Hello claimant {user['email']}"}