"""FastAPI claim endpoints — Steps 1–3 only (no LLM)."""

from __future__ import annotations

import json
from typing import Any

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.models.states import InvalidStateTransition
from app.schemas.claims import (
    CreateClaimResponse,
    PrepareResponse,
    RehydrateRequest,
    RehydrateResponse,
    SanitizeResponse,
    UploadInputsResponse,
    ValidateResponse,
)
from app.security.auth import AuthenticatedCaller, Role, require_roles
from app.services.ingestion.service import ClaimService

router = APIRouter(prefix="/claims", tags=["claims"])

_service: ClaimService | None = None


def get_claim_service() -> ClaimService:
    global _service
    if _service is None:
        # Drop stale settings/encryption caches after uvicorn reload
        from app.config.settings import get_settings
        from app.services.encryption.provider import get_encryption_provider

        get_settings.cache_clear()
        get_encryption_provider.cache_clear()
        _service = ClaimService()
    return _service


def set_claim_service(service: ClaimService) -> None:
    global _service
    _service = service


@router.post("", response_model=CreateClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> CreateClaimResponse:
    session = service.create_session()
    return CreateClaimResponse(session_id=session.session_id, state=session.state)


@router.get("/{session_id}")
def get_session(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> dict[str, Any]:
    """Return session status and sanitised artefacts only (never the mapping)."""
    try:
        session = service._get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    docs_dir = service.storage.sanitised_dir(session_id) / "documents"
    sanitised_documents: list[dict[str, Any]] = []
    if docs_dir.exists():
        names = {p.name for p in docs_dir.iterdir() if p.is_file()}
        for path in sorted(docs_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".txt", ".json"}:
                continue
            # Prefer visual .sanitised.pdf over a stale .withheld.pdf notice
            lower = path.name.lower()
            if lower.endswith(".withheld.pdf"):
                stem = path.name[: -len(".withheld.pdf")]
                if f"{stem}.sanitised.pdf" in names:
                    continue
            sanitised_documents.append(
                {
                    "filename": path.name,
                    "size": path.stat().st_size,
                    "kind": "pdf" if path.suffix.lower() == ".pdf" else "text",
                }
            )

    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "inputs": [
            {
                "input_id": i.input_id,
                "kind": i.kind.value,
                "original_filename": i.original_filename,
                "content_type": i.content_type,
                "metadata": i.metadata,
            }
            for i in session.inputs
        ],
        "sanitised_documents": sanitised_documents,
        "image_results": [r.model_dump() for r in session.image_results],
        "text_result": session.text_result.model_dump() if session.text_result else None,
        "validation": session.validation.model_dump() if session.validation else None,
        "package_path": session.package_path,
        "llm_payload_path": session.llm_payload_path,
        "error_message": session.error_message,
    }


@router.post("/{session_id}/inputs", response_model=UploadInputsResponse)
async def upload_inputs(
    session_id: str,
    claim_json: str | None = Form(default=None),
    document_type: str = Form(default="DOCUMENT"),
    files: list[UploadFile] | None = File(default=None),
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> UploadInputsResponse:
    try:
        session = service._get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    received: list[dict[str, Any]] = []
    try:
        if claim_json:
            claim = json.loads(claim_json)
            inp = service.add_claim_record(session_id, claim)
            received.append({"input_id": inp.input_id, "kind": inp.kind.value})

        for upload in files or []:
            data = await upload.read()
            filename = upload.filename or "upload.bin"
            content_type = upload.content_type or ""
            if content_type.startswith("image/") or filename.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")
            ):
                inp = service.add_image(session_id, filename, data, content_type)
            else:
                doc_type = "PDS" if "pds" in filename.lower() else document_type
                inp = service.add_document(
                    session_id,
                    filename,
                    data,
                    document_type=doc_type,
                    content_type=content_type,
                )
            received.append({"input_id": inp.input_id, "kind": inp.kind.value})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = service._get(session_id)
    return UploadInputsResponse(
        session_id=session_id,
        state=session.state,
        received_inputs=received,
    )


@router.post("/{session_id}/sanitize", response_model=SanitizeResponse)
def sanitize_claim(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(require_roles(Role.PII_PROCESSOR, Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> SanitizeResponse:
    try:
        session = service.sanitize(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        session = service._get(session_id)
        return SanitizeResponse(
            session_id=session_id,
            state=session.state,
            image_results=session.image_results,
            text_result=session.text_result,
            error_message=str(exc),
        )
    return SanitizeResponse(
        session_id=session_id,
        state=session.state,
        image_results=session.image_results,
        text_result=session.text_result,
        error_message=session.error_message,
    )


@router.post("/{session_id}/validate", response_model=ValidateResponse)
def validate_claim(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(require_roles(Role.PII_PROCESSOR, Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> ValidateResponse:
    try:
        session = service.validate(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    assert session.validation is not None
    return ValidateResponse(
        session_id=session_id,
        state=session.state,
        validation=session.validation,
    )


@router.post("/{session_id}/prepare", response_model=PrepareResponse)
def prepare_claim(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(require_roles(Role.PII_PROCESSOR, Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> PrepareResponse:
    try:
        session = service.prepare(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PrepareResponse(
        session_id=session_id,
        state=session.state,
        package_path=session.package_path,
        llm_payload_path=session.llm_payload_path,
    )


@router.get("/{session_id}/sanitised-images/{filename}")
def get_sanitised_image(
    session_id: str,
    filename: str,
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> FileResponse:
    """Serve a sanitised image for UI preview (never raw uploads)."""
    try:
        service._get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = service.storage.sanitised_dir(session_id) / "images" / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Sanitised image not found")
    return FileResponse(path, media_type="image/jpeg", filename=safe_name)


@router.get("/{session_id}/sanitised-documents/{filename}")
def get_sanitised_document(
    session_id: str,
    filename: str,
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> FileResponse:
    """Serve a sanitised document (redacted PDF/text) for preview/download."""
    try:
        service._get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = service.storage.sanitised_dir(session_id) / "documents" / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Sanitised document not found")
    suffix = path.suffix.lower()
    media = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=safe_name)


@router.get("/{session_id}/llm-payload")
def get_llm_payload(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(
        require_roles(Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN)
    ),
    service: ClaimService = Depends(get_claim_service),
) -> dict[str, Any]:
    try:
        return service.get_llm_payload(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{session_id}/rehydrate", response_model=RehydrateResponse)
def rehydrate(
    session_id: str,
    body: RehydrateRequest,
    _caller: AuthenticatedCaller = Depends(require_roles(Role.PII_REHYDRATOR, Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> RehydrateResponse:
    from app.services.retention.service import MappingExpiredError

    try:
        session, result = service.rehydrate(
            session_id,
            body.content,
            body.rehydration_policy,
            body.allowed_entities,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MappingExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=403, detail="ACCESS_DENIED") from exc

    return RehydrateResponse(
        session_id=session_id,
        state=session.state,
        status=result["status"],
        rehydrated=result["rehydrated"],
        unknown_placeholders=result["unknown_placeholders"],
        policy=body.rehydration_policy,
    )


@router.get("/{session_id}/audit")
def get_audit_trail(
    session_id: str,
    _caller: AuthenticatedCaller = Depends(require_roles(Role.AUDITOR, Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> dict[str, Any]:
    """Return PII-scrubbed audit events for a session (AUDITOR role)."""
    try:
        service._get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    from app.services.audit.logger import get_audit_logger

    events = get_audit_logger().events_for_session(session_id)
    return {"session_id": session_id, "events": events}


@router.post("/admin/retention/sweep")
def retention_sweep(
    _caller: AuthenticatedCaller = Depends(require_roles(Role.ADMIN)),
    service: ClaimService = Depends(get_claim_service),
) -> dict[str, Any]:
    counts = service.retention.sweep()
    return {"status": "ok", "removed": counts}
