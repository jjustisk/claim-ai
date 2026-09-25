"""PII Reduction Service — Steps 1–3 only. No LLM dependencies."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope, Receive, Send

from app.api.claims import router as claims_router
from app.config.settings import get_settings


def _ui_dir() -> Path:
    # Prefer repo-root /ui, fall back to pii_reduction/ui
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "ui",  # pii-d-r/ui
        here.parents[1] / "ui",  # pii_reduction/ui
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


class NoCacheStaticFiles(StaticFiles):
    """Always revalidate UI assets so Output PDF cards aren't stuck on old HTML."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_no_cache(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"etag", b"last-modified", b"cache-control"}
                ]
                headers.append((b"cache-control", b"no-store, max-age=0"))
                message = {**message, "headers": headers}
            await send(message)

        await super().__call__(scope, receive, send_no_cache)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    for path in settings.storage_paths().values():
        path.mkdir(parents=True, exist_ok=True)
    # Surface EgoBlur readiness early (torch missing → OpenCV fallback)
    from app.services.image_redaction import egoblur_engine
    from app.services.image_redaction.plates import EgoBlurPlateRedactor
    from app.services.retention.service import RetentionService

    plates = EgoBlurPlateRedactor(
        model_path=settings.egoblur_lp_model_path,
        score_threshold=settings.egoblur_lp_score_threshold,
    )
    import logging

    logging.getLogger("pii_reduction").info(
        "Plate redaction: egoblur_ready=%s model=%s torch=%s",
        plates._egoblur_available(),
        plates.model_path,
        egoblur_engine.egoblur_runtime_available(),
    )
    try:
        swept = RetentionService(settings).sweep()
        logging.getLogger("pii_reduction").info("Retention sweep on startup: %s", swept)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("pii_reduction").warning("Retention sweep failed: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Secure PII protection for insurance claims. "
            "Produces LLM-ready sanitised packages. Does not call or load any LLM."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(claims_router, prefix=settings.api_prefix)

    ui_path = _ui_dir()
    if ui_path.is_dir():
        app.mount("/ui", NoCacheStaticFiles(directory=str(ui_path), html=True), name="ui")

        @app.get("/")
        def root() -> RedirectResponse:
            return RedirectResponse(url="/ui/input.html?v=2")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "llm": "disabled"}

    return app


app = create_app()
