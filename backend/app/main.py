from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base
import app.schema

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan, title="Claim AI API", version="0.0.1")

@app.get("/health")
def health() -> dict:
    """Basic liveness check. Extend later to also ping the database."""
    return {"status": "ok"}
