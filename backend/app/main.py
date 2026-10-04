from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

import app.api.schemas.models
from app.api.routers import auth as auth_router
from app.api.routers import claims as claims_router
from app.api.routers import policies as policies_router
from app.config import settings
from app.connectors.db import Base, engine
from app.connectors.storage import close_blob_service_client
from app.security import SecurityHeadersMiddleware, is_production, trusted_hosts
from app.services.claim_pipeline_queue import (
    start_claim_pipeline_worker,
    stop_claim_pipeline_worker,
)
from app.services.claim_pii_service import ensure_claim_pii_columns
from app.services.claim_service import (
    ensure_claim_document_phash_column,
    ensure_claim_form_columns,
    ensure_policy_customer_column,
)

logger = logging.getLogger("claim_ai")

_PROD_INTERNAL_ERROR = "Something went wrong on our side. Please try again shortly."
_PROD_VALIDATION_ERROR = "Some details could not be validated. Please review and try again."


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_claim_form_columns()
    ensure_policy_customer_column()
    ensure_claim_document_phash_column()
    ensure_claim_pii_columns()
    await start_claim_pipeline_worker()
    yield
    await stop_claim_pipeline_worker()
    await close_blob_service_client()


_docs_url = "/docs" if settings.openapi_docs_enabled() else None
_redoc_url = "/redoc" if settings.openapi_docs_enabled() else None
_openapi_url = "/openapi.json" if settings.openapi_docs_enabled() else None

app = FastAPI(
    lifespan=lifespan,
    title="Claim AI API",
    version="0.0.1",
    description="JSON API for the Vue frontend.",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    max_age=600,
)
_hosts = trusted_hosts()
if _hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

app.include_router(auth_router.router, prefix="/api")
app.include_router(claims_router.router, prefix="/api")
app.include_router(policies_router.router, prefix="/api")

if settings.test_ui_enabled():
    from app.pages import orchestration_test as orchestration_test_pages
    from app.pages import pds_search as pds_search_pages
    from app.pages import portal as portal_pages
    from app.pages import storage as storage_pages
    from app.pages import test_claim_form as test_claim_form_pages

    app.include_router(portal_pages.router)
    app.include_router(storage_pages.router)
    app.include_router(pds_search_pages.router)
    app.include_router(orchestration_test_pages.router)
    app.include_router(test_claim_form_pages.router)


def _safe_http_detail(detail: object, status_code: int) -> object:
    """Keep intentional public messages; never return HTML or huge dumps."""
    if isinstance(detail, str):
        text = detail.strip()
        if not text:
            return _PROD_INTERNAL_ERROR if status_code >= 500 else _PROD_VALIDATION_ERROR
        lowered = text.lower()
        if "<html" in lowered or "<!doctype" in lowered or "<pre" in lowered:
            return _PROD_INTERNAL_ERROR if status_code >= 500 else _PROD_VALIDATION_ERROR
        if is_production() and status_code >= 500:
            return _PROD_INTERNAL_ERROR
        if len(text) > 240 and is_production():
            return _PROD_INTERNAL_ERROR if status_code >= 500 else _PROD_VALIDATION_ERROR
        return text
    if isinstance(detail, list):
        return detail
    if detail is None:
        return _PROD_INTERNAL_ERROR if status_code >= 500 else _PROD_VALIDATION_ERROR
    if is_production() and status_code >= 500:
        return _PROD_INTERNAL_ERROR
    return str(detail)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _safe_http_detail(exc.detail, exc.status_code)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    if is_production():
        return JSONResponse(status_code=422, content={"detail": _PROD_VALIDATION_ERROR})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled API error: %s", exc)
    if is_production():
        return JSONResponse(status_code=500, content={"detail": _PROD_INTERNAL_ERROR})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/")
def root():
    """Production serves the Vue SPA via nginx; API root is a JSON pointer."""
    if settings.test_ui_enabled():
        return RedirectResponse("/ui")
    return JSONResponse(
        {
            "service": "claim-ai-api",
            "status": "ok",
            "docs": bool(_docs_url),
            "health": "/health",
        }
    )


@app.get("/health")
def health() -> dict:
    """Liveness check for local runs and Azure health probes."""
    return {"status": "ok", "environment": "production" if is_production() else "development"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}
