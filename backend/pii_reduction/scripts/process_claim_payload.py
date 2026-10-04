"""Run PII reduction on a claim payload (stdin JSON → stdout JSON).

Invoked from the main Claim AI API with cwd=backend/pii_reduction and
PYTHONPATH including that directory so `app.*` resolves to this service.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

# Ensure pii_reduction root is on path when run as a script
_PII_ROOT = Path(__file__).resolve().parents[1]
if str(_PII_ROOT) not in sys.path:
    sys.path.insert(0, str(_PII_ROOT))

from app.config.settings import Settings, get_settings  # noqa: E402
from app.models.session import InputKind  # noqa: E402
from app.services.ingestion.service import ClaimService  # noqa: E402
from app.services.storage.session_store import SessionStorage  # noqa: E402


IMAGE_TYPES = {"image/jpeg", "image/png"}


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("Expected JSON payload on stdin")
    return json.loads(raw)


def _image_bytes(session_id: str, storage: SessionStorage, result_path: str) -> bytes:
    path = Path(result_path)
    if not path.is_absolute():
        path = storage.sanitised_dir(session_id) / path
    return path.read_bytes()


def run(payload: dict[str, Any]) -> dict[str, Any]:
    claim_id = payload.get("claim_id")
    claim_record: dict[str, Any] = payload.get("claim_record") or {}
    files: list[dict[str, Any]] = payload.get("files") or []

    get_settings.cache_clear()
    data_root = _PII_ROOT / "data" / "claim_sessions" / str(claim_id or "unknown")
    settings = Settings(
        data_root=data_root,
        metadata_backend=payload.get("metadata_backend") or "pillow",
        ocr_backend=payload.get("ocr_backend") or "noop",
        redaction_backend=payload.get("redaction_backend") or "opencv",
    )
    storage = SessionStorage(settings)
    service = ClaimService(settings=settings, storage=storage)

    session = service.create_session()
    session_id = session.session_id
    service.add_claim_record(session_id, claim_record)

    doc_id_by_input: dict[str, int] = {}
    for item in files:
        doc_id = int(item["doc_id"])
        filename = item.get("filename") or "file"
        content_type = item.get("content_type") or "application/octet-stream"
        data = base64.b64decode(item["data_b64"])

        if content_type in IMAGE_TYPES:
            inp = service.add_image(session_id, filename, data, content_type)
            doc_id_by_input[inp.input_id] = doc_id
        elif content_type == "application/pdf":
            inp = service.add_document(
                session_id, filename, data, document_type="EVIDENCE", content_type=content_type
            )
            doc_id_by_input[inp.input_id] = doc_id
        else:
            continue

    session = service.sanitize(session_id)
    session = service.validate(session_id)
    validation_passed = bool(session.validation and session.validation.passed)
    if validation_passed:
        session = service.prepare(session_id)
        llm_payload = service.get_llm_payload(session_id)
    else:
        llm_payload = None

    sanitised_files: list[dict[str, Any]] = []
    for result in session.image_results:
        doc_id = doc_id_by_input.get(result.input_id)
        if doc_id is None or not result.sanitised_path:
            continue
        body = _image_bytes(session_id, storage, result.sanitised_path)
        inp = next(
            (i for i in session.inputs if i.input_id == result.input_id and i.kind == InputKind.IMAGE),
            None,
        )
        content_type = (inp.content_type if inp else None) or "image/jpeg"
        sanitised_files.append(
            {
                "doc_id": doc_id,
                "content_type": content_type,
                "data_b64": base64.b64encode(body).decode("ascii"),
            }
        )

    failures: list[str] = []
    if session.validation:
        failures = list(session.validation.failures)

    return {
        "session_id": session_id,
        "validation_passed": validation_passed,
        "validation_failures": failures,
        "llm_payload": llm_payload,
        "sanitised_files": sanitised_files,
        "state": session.state.value,
        "error_message": session.error_message,
    }


def main() -> None:
    try:
        payload = _read_stdin()
        out = run(payload)
        json.dump(out, sys.stdout)
    except Exception as exc:  # noqa: BLE001
        json.dump({"error": str(exc), "validation_passed": False}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
