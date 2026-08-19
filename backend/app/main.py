from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

import app.api.schemas.models
from app.api.routers import auth as auth_router
from app.api.routers import claims as claims_router
from app.api.routers import policies as policies_router
from app.config import settings
from app.connectors.db import Base, engine
from app.connectors.storage import close_blob_service_client
from app.pages import portal as portal_pages
from app.pages import storage as storage_pages


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_blob_service_client()


app = FastAPI(
    lifespan=lifespan,
    title="Claim AI API",
    version="0.0.1",
    description="JSON API for the Vue frontend. HTML under /ui is a temporary test UI.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api")
app.include_router(claims_router.router, prefix="/api")
app.include_router(policies_router.router, prefix="/api")
app.include_router(portal_pages.router)
app.include_router(storage_pages.router)


@app.get("/")
def root() -> RedirectResponse:
    """Temporary: send people to the test UI. Remove when Vue owns /."""
    return RedirectResponse("/ui")


@app.get("/health")
def health() -> dict:
    """Liveness check for local runs and later Azure health probes."""
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}
