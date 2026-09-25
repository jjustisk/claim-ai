"""Step 3 — sanitisation validation, package & payload builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.session import ClaimSession, ValidationReport
from app.services.audit.logger import get_audit_logger
from app.services.storage.session_store import SessionStorage


class SanitisationValidator:
    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()
        self.audit = get_audit_logger()

    def validate(self, session: ClaimSession) -> ValidationReport:
        checks: dict[str, bool] = {}
        failures: list[str] = []

        checks["inputs_present"] = len(session.inputs) > 0
        if not checks["inputs_present"]:
            failures.append("No inputs were received")

        image_inputs = [i for i in session.inputs if i.kind.value == "image"]
        if image_inputs:
            checks["images_processed"] = len(session.image_results) >= len(image_inputs)
            if not checks["images_processed"]:
                failures.append("Not all images were processed")

            checks["metadata_sanitised"] = all(r.metadata_sanitised for r in session.image_results)
            if not checks["metadata_sanitised"]:
                failures.append("One or more images failed metadata sanitisation")

            checks["faces_handled"] = all(
                r.faces_redacted == r.faces_detected for r in session.image_results
            )
            if not checks["faces_handled"]:
                failures.append("Detected faces were not fully redacted")

            checks["plates_handled"] = all(
                r.plates_redacted == r.plates_detected for r in session.image_results
            )
            if not checks["plates_handled"]:
                failures.append("Detected plates were not fully redacted")

            checks["ocr_completed"] = all(r.ocr_completed for r in session.image_results)
            if not checks["ocr_completed"]:
                failures.append("OCR did not complete for all images")

            critical_image_errors = [
                e for r in session.image_results for e in r.errors if "failed" in e
            ]
            checks["no_critical_image_errors"] = len(critical_image_errors) == 0
            if critical_image_errors:
                failures.extend(critical_image_errors)
        else:
            checks["images_processed"] = True
            checks["metadata_sanitised"] = True
            checks["faces_handled"] = True
            checks["plates_handled"] = True
            checks["ocr_completed"] = True
            checks["no_critical_image_errors"] = True

        checks["text_pii_completed"] = session.text_result is not None
        if not checks["text_pii_completed"]:
            failures.append("Text PII detection did not complete")

        mapping = self.storage.load_mapping(session.session_id)
        checks["mapping_stored"] = True  # empty mapping is valid if no PII
        if session.text_result and session.text_result.placeholders_created > 0:
            checks["mapping_stored"] = len(mapping) > 0
            if not checks["mapping_stored"]:
                failures.append("Placeholder mapping was not securely stored")

        checks["placeholders_generated"] = session.text_result is not None
        # Mapping must never live under llm-ready
        llm_dir = self.storage.llm_ready_dir(session.session_id)
        mapping_leak = list(llm_dir.rglob("mapping*")) if llm_dir.exists() else []
        checks["mapping_isolated"] = len(mapping_leak) == 0
        if mapping_leak:
            failures.append("Placeholder mapping found in LLM-ready area")

        passed = all(checks.values())
        report = ValidationReport(passed=passed, checks=checks, failures=failures)
        self.audit.log(
            "VALIDATION_COMPLETED",
            session_id=session.session_id,
            passed=passed,
            failure_count=len(failures),
        )
        return report


class PackageBuilder:
    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()
        self.audit = get_audit_logger()

    def build(self, session: ClaimSession) -> Path:
        package_dir = self.storage.copy_to_package(session.session_id)
        # Ensure claim.json + metadata.json exist
        claim_path = package_dir / "claim.json"
        if not claim_path.exists() and session.text_result:
            claim_path.write_text(
                json.dumps(session.text_result.sanitised_claim, indent=2),
                encoding="utf-8",
            )
        meta = {
            "session_id": session.session_id,
            "state": session.state.value,
            "image_count": len(session.image_results),
            "input_count": len(session.inputs),
        }
        (package_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        session.package_path = str(package_dir)
        self.audit.log("SANITIZATION_COMPLETED", session_id=session.session_id)
        return package_dir


class PayloadBuilder:
    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()
        self.audit = get_audit_logger()

    def build(self, session: ClaimSession) -> dict[str, Any]:
        claim = session.text_result.sanitised_claim if session.text_result else {}
        images = []
        for idx, result in enumerate(session.image_results, start=1):
            images.append(
                {
                    "image_id": f"IMG_{idx:03d}",
                    "path": result.sanitised_path,
                    "ocr_path": result.ocr_path,
                }
            )
        documents = []
        for inp in session.inputs:
            if inp.kind.value == "document":
                documents.append(
                    {
                        "document_id": inp.input_id,
                        "type": inp.metadata.get("document_type", "DOCUMENT"),
                        "filename": inp.original_filename,
                    }
                )

        payload = {
            "session_id": session.session_id,
            "status": "READY_FOR_LLM",
            "claim": claim,
            "documents": documents,
            "images": images,
        }
        path = self.storage.write_llm_payload(session.session_id, payload)
        session.llm_payload_path = str(path)
        self.audit.log("LLM_PAYLOAD_CREATED", session_id=session.session_id)
        return payload
