"""Bridge claim submission to the PII reduction pipeline.

Workflow: raw claim + uploads stay in DB/blob storage; a subprocess runs the
PII service and returns sanitised images plus an LLM-ready payload. Downstream
AI stages must use only those artefacts (never raw file_url / ORM text).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDocument
from app.connectors.db import get_sync_connection
from app.connectors.storage import download_stored_blob, upload_image

logger = logging.getLogger(__name__)

PII_ROOT = Path(__file__).resolve().parents[2] / "pii_reduction"
PII_SCRIPT = PII_ROOT / "scripts" / "process_claim_payload.py"
IMAGE_FILE_TYPES = ("image/jpeg", "image/png")
PDF_TYPE = "application/pdf"
PII_STATUS_READY = "ready"
SANITISED_BLOB_DIR = "/sanitised/"
_PLACEHOLDER_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]*_\d+)\b")


class PiiReductionError(Exception):
    """PII reduction did not produce an LLM-safe payload."""


class PiiNotReadyError(PiiReductionError):
    """Claim has not completed PII reduction yet."""


def _log_pii_failure(
    claim_id: int,
    reason: str,
    *,
    detail: str | None = None,
    exc: BaseException | None = None,
) -> None:
    """Emit visible terminal logs when PII reduction does not succeed."""
    if exc is not None:
        logger.error(
            "PII reduction FAILED claim_id=%s: %s",
            claim_id,
            reason,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    else:
        logger.error("PII reduction FAILED claim_id=%s: %s", claim_id, reason)
    if detail:
        logger.error("PII reduction detail claim_id=%s:\n%s", claim_id, detail.rstrip())


def ensure_claim_pii_columns() -> None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE claim ADD COLUMN IF NOT EXISTS pii_session_id VARCHAR(64)")
            cur.execute("ALTER TABLE claim ADD COLUMN IF NOT EXISTS pii_status VARCHAR(32)")
            cur.execute("ALTER TABLE claim ADD COLUMN IF NOT EXISTS llm_payload_json TEXT")
            cur.execute("ALTER TABLE claim_document ADD COLUMN IF NOT EXISTS sanitised_file_url TEXT")
        conn.commit()
    finally:
        conn.close()


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def claim_to_pii_record(claim: Claim) -> dict[str, Any]:
    """Flat claim JSON for Presidio / schema-aware redaction."""
    skip = {
        "claim_id",
        "pii_session_id",
        "pii_status",
        "llm_payload_json",
    }
    out: dict[str, Any] = {}
    for column in Claim.__table__.columns:
        key = column.name
        if key in skip:
            continue
        out[key] = _serialize_value(getattr(claim, key))
    out["claim_id"] = claim.claim_reference
    return out


def get_llm_payload_from_claim(claim: Claim) -> dict[str, Any] | None:
    raw = getattr(claim, "llm_payload_json", None)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _normalise_blob_path(path: str | None) -> str:
    return (path or "").strip().replace("\\", "/")


def llm_payload_is_ai_safe(payload: dict[str, Any] | None) -> bool:
    """Reject demo / bypass payloads that must never feed model calls."""
    if not payload:
        return False
    status = str(payload.get("status") or "").upper()
    if status.startswith("DEMO") or "UNREDACTED" in status:
        return False
    if payload.get("_demo_warning") or payload.get("_demo_pii_failure"):
        return False
    if payload.get("demo_note"):
        return False
    return bool(payload.get("claim"))


def sanitised_image_blob_is_ai_safe(
    sanitised_path: str | None,
    *,
    original_path: str | None,
) -> bool:
    """Sanitised blobs must live under .../sanitised/ and must not be the upload path."""
    sanitised = _normalise_blob_path(sanitised_path)
    original = _normalise_blob_path(original_path)
    if not sanitised:
        return False
    if SANITISED_BLOB_DIR not in f"/{sanitised.lstrip('/')}":
        return False
    if original and sanitised == original:
        return False
    return True


def sanitised_image_blob_for_ai(document: ClaimDocument) -> str:
    """Return the blob path Call 1 may download, or raise if not PII-reduced."""
    path = document.sanitised_file_url
    if not sanitised_image_blob_is_ai_safe(path, original_path=document.file_url):
        raise PiiNotReadyError(
            f"Document {document.doc_id} has no AI-safe sanitised image "
            f"(sanitised_file_url={path!r})."
        )
    return _normalise_blob_path(path)


def claim_pii_is_ready(claim: Claim) -> bool:
    """True only when PII reduction completed and produced an LLM-safe payload."""
    if getattr(claim, "pii_status", None) != PII_STATUS_READY:
        return False
    payload = get_llm_payload_from_claim(claim)
    return llm_payload_is_ai_safe(payload)


async def ensure_image_documents_sanitised_for_ai(claim_id: int, db: AsyncSession) -> None:
    """Every claim image must have a distinct sanitised blob before any model sees it."""
    result = await db.execute(
        select(ClaimDocument).where(
            ClaimDocument.claim_id == claim_id,
            ClaimDocument.file_type.in_(IMAGE_FILE_TYPES),
        )
    )
    documents = result.scalars().all()
    for doc in documents:
        sanitised_image_blob_for_ai(doc)


async def ensure_claim_ready_for_ai(claim_id: int, db: AsyncSession) -> dict[str, Any]:
    """Gate for all post-PII model stages (text payload + sanitised images)."""
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise PiiNotReadyError(f"Claim {claim_id} not found.")
    record = sanitised_claim_record(claim)
    await ensure_image_documents_sanitised_for_ai(claim_id, db)
    payload = get_llm_payload_from_claim(claim)
    assert payload is not None
    return {"claim": record, "payload": payload}


def sanitised_claim_record(claim: Claim) -> dict[str, Any]:
    if not claim_pii_is_ready(claim):
        status = getattr(claim, "pii_status", None) or "unknown"
        raise PiiNotReadyError(
            f"Claim {claim.claim_id} is not PII-ready (status={status}). "
            "AI stages cannot run until reduction succeeds."
        )
    payload = get_llm_payload_from_claim(claim)
    assert payload is not None
    return payload.get("claim") or {}


def sanitised_free_text(claim: Claim, *field_names: str) -> str:
    record = sanitised_claim_record(claim)
    parts = [str(record[f]).strip() for f in field_names if record.get(f)]
    return "\n\n".join(parts) if parts else "(No claimant description provided.)"


def load_pii_mapping_for_claim(claim_id: int, session_id: str | None) -> dict[str, str]:
    """Load the encrypted placeholder→original mapping for an assessor rehydrate."""
    if not session_id:
        return {}
    mapping_path = (
        PII_ROOT
        / "data"
        / "claim_sessions"
        / str(claim_id)
        / "secure-mapping"
        / session_id
        / "mapping.enc"
    )
    if not mapping_path.is_file():
        return {}
    try:
        from cryptography.fernet import Fernet

        key_file = PII_ROOT / "data" / ".fernet_key"
        env_key = os.environ.get("CLAIM_AI_ENCRYPTION_KEY") or os.environ.get("ENCRYPTION_KEY")
        if env_key and env_key.strip():
            key = env_key.strip().encode("ascii")
        elif key_file.is_file():
            key = key_file.read_text(encoding="ascii").strip().encode("ascii")
        else:
            logger.warning("No PII encryption key available to rehydrate claim_id=%s", claim_id)
            return {}
        raw = Fernet(key).decrypt(mapping_path.read_bytes())
        mapping = json.loads(raw.decode("utf-8"))
        return mapping if isinstance(mapping, dict) else {}
    except Exception:
        logger.exception(
            "Failed to load PII mapping for claim_id=%s session=%s", claim_id, session_id
        )
        return {}


def rehydrate_assessor_text(
    text: str,
    *,
    claim_id: int,
    session_id: str | None,
    mapping: dict[str, str] | None = None,
) -> str:
    """Replace ADDRESS_1 / EMAIL_1 style tokens with originals for assessor-facing docs."""
    if not text:
        return text
    mapping = mapping if mapping is not None else load_pii_mapping_for_claim(claim_id, session_id)
    if not mapping:
        return text

    def _repl(match: re.Match[str]) -> str:
        token = match.group(1)
        return str(mapping.get(token, token))

    return _PLACEHOLDER_TOKEN.sub(_repl, text)


def _run_pii_subprocess(payload: dict[str, Any]) -> dict[str, Any]:
    claim_id = int(payload.get("claim_id") or 0)
    if not PII_SCRIPT.is_file():
        msg = f"PII script not found: {PII_SCRIPT}"
        _log_pii_failure(claim_id, msg)
        raise PiiReductionError(msg)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PII_ROOT) + (os.pathsep + env.get("PYTHONPATH", ""))

    logger.info(
        "PII reduction starting claim_id=%s files=%s python=%s",
        claim_id,
        len(payload.get("files") or []),
        sys.executable,
    )

    proc = subprocess.run(
        [sys.executable, str(PII_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(PII_ROOT),
        env=env,
        timeout=600,
    )
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        msg = stderr or f"exit code {proc.returncode}"
        _log_pii_failure(claim_id, f"PII subprocess failed: {msg}", detail=stderr)
        raise PiiReductionError(f"PII subprocess failed: {msg}")
    if proc.returncode != 0 and stderr:
        logger.warning(
            "PII subprocess exited %s claim_id=%s (stdout present); stderr:\n%s",
            proc.returncode,
            claim_id,
            stderr[-4000:],
        )

    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        _log_pii_failure(
            claim_id,
            f"Invalid PII subprocess output: {exc}",
            detail=(proc.stdout or "")[:2000],
            exc=exc,
        )
        raise PiiReductionError(f"Invalid PII subprocess output: {exc}") from exc

    if result.get("error"):
        err = str(result["error"])
        _log_pii_failure(claim_id, err, detail=stderr)
        raise PiiReductionError(err)
    return result


async def run_pii_reduction_for_claim(claim_id: int, db: AsyncSession) -> dict[str, Any]:
    """Run full PII pipeline for a claim and persist sanitised artefacts."""
    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise PiiReductionError(f"Claim {claim_id} not found.")

    if claim_pii_is_ready(claim):
        try:
            await ensure_image_documents_sanitised_for_ai(claim_id, db)
        except PiiNotReadyError as exc:
            claim.pii_status = "failed"
            claim.llm_payload_json = None
            await db.commit()
            msg = f"Invalid or stale PII artefacts: {exc}"
            _log_pii_failure(claim_id, msg, exc=exc)
            raise PiiReductionError(msg) from exc
        stored = get_llm_payload_from_claim(claim)
        if stored:
            return stored

    result = await db.execute(
        select(ClaimDocument).where(ClaimDocument.claim_id == claim_id).order_by(ClaimDocument.doc_id)
    )
    documents = result.scalars().all()

    files_payload: list[dict[str, Any]] = []
    for doc in documents:
        if doc.file_type not in (*IMAGE_FILE_TYPES, PDF_TYPE):
            continue
        raw = await download_stored_blob(doc.file_url)
        files_payload.append(
            {
                "doc_id": doc.doc_id,
                "filename": Path(doc.file_url).name,
                "content_type": doc.file_type,
                "data_b64": base64.b64encode(raw).decode("ascii"),
            }
        )

    claim.pii_status = "processing"
    await db.commit()

    subprocess_payload = {
        "claim_id": claim_id,
        "claim_record": claim_to_pii_record(claim),
        "files": files_payload,
    }

    try:
        pii_out = await asyncio.to_thread(_run_pii_subprocess, subprocess_payload)
    except PiiReductionError:
        claim.pii_status = "failed"
        claim.llm_payload_json = None
        await db.commit()
        raise
    except Exception as exc:
        claim.pii_status = "failed"
        claim.llm_payload_json = None
        await db.commit()
        _log_pii_failure(claim_id, "PII subprocess raised unexpectedly", exc=exc)
        raise PiiReductionError(str(exc)) from exc

    if pii_out.get("error_message"):
        reason = str(pii_out["error_message"])
        claim.pii_session_id = pii_out.get("session_id")
        claim.pii_status = "failed"
        claim.llm_payload_json = None
        await db.commit()
        _log_pii_failure(
            claim_id,
            reason,
            detail=f"session_id={pii_out.get('session_id')} state={pii_out.get('state')}",
        )
        raise PiiReductionError(reason)

    if not pii_out.get("validation_passed") or not pii_out.get("llm_payload"):
        failures = pii_out.get("validation_failures") or ["PII validation failed"]
        reason = "; ".join(failures)
        claim.pii_session_id = pii_out.get("session_id")
        claim.pii_status = "failed"
        claim.llm_payload_json = None
        await db.commit()
        _log_pii_failure(
            claim_id,
            reason,
            detail="\n".join(f"- {f}" for f in failures),
        )
        raise PiiReductionError(reason)

    llm_payload = pii_out["llm_payload"]
    claim.pii_session_id = pii_out.get("session_id")
    claim.pii_status = PII_STATUS_READY
    claim.llm_payload_json = json.dumps(llm_payload)

    sanitised_by_doc: dict[int, str] = {}
    for item in pii_out.get("sanitised_files") or []:
        doc_id = int(item["doc_id"])
        doc = await db.get(ClaimDocument, doc_id)
        if doc is None:
            continue
        content_type = item.get("content_type") or "image/jpeg"
        body = base64.b64decode(item["data_b64"])
        blob_name = f"claim-{claim_id}/sanitised/{doc_id}-{Path(doc.file_url).name}"
        await upload_image(blob_name, body, content_type=content_type, overwrite=True)
        if not sanitised_image_blob_is_ai_safe(blob_name, original_path=doc.file_url):
            msg = f"Refusing to store non-sanitised blob path for document {doc_id}"
            _log_pii_failure(claim_id, msg)
            raise PiiReductionError(msg)
        doc.sanitised_file_url = blob_name
        sanitised_by_doc[doc_id] = blob_name

    image_doc_ids = [
        doc.doc_id
        for doc in documents
        if doc.file_type in IMAGE_FILE_TYPES
    ]
    missing = [doc_id for doc_id in image_doc_ids if doc_id not in sanitised_by_doc]
    if missing:
        claim.pii_status = "failed"
        claim.llm_payload_json = None
        await db.commit()
        msg = f"PII reduction did not produce sanitised images for document(s): {missing}"
        _log_pii_failure(claim_id, msg)
        raise PiiReductionError(msg)

    await db.commit()
    logger.info("PII reduction succeeded claim_id=%s session_id=%s", claim_id, claim.pii_session_id)
    return llm_payload
