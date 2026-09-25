"""Claim ingestion and orchestration service (Steps 1–3)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.config.settings import DEFAULT_CLAIM_SCHEMA, Settings, get_settings
from app.models.session import ClaimSession, InputKind, SessionInput, TextSanitizationResult
from app.models.states import ClaimState, InvalidStateTransition, transition
from app.schemas.claims import RehydrationPolicy
from app.services.audit.logger import get_audit_logger
from app.services.documents.sanitizer import DocumentSanitizer, build_redacted_pdf
from app.services.image_redaction.pipeline import SUPPORTED_IMAGE_EXTENSIONS, ImageRedactionPipeline
from app.services.ingestion.session_ids import generate_session_id
from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry
from app.services.rehydration.service import RehydrationService
from app.services.retention.service import MappingExpiredError, RetentionService
from app.services.secure_processing.validator import PackageBuilder, PayloadBuilder, SanitisationValidator
from app.services.storage.session_store import SessionStorage


class ClaimService:
    def __init__(
        self,
        settings: Settings | None = None,
        storage: SessionStorage | None = None,
        image_pipeline: ImageRedactionPipeline | None = None,
        pii: PIIDetector | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or SessionStorage(self.settings)
        self.image_pipeline = image_pipeline or ImageRedactionPipeline(self.settings)
        self.pii = pii or PIIDetector(self.settings)
        self.validator = SanitisationValidator(self.storage)
        self.package_builder = PackageBuilder(self.storage)
        self.payload_builder = PayloadBuilder(self.storage)
        self.rehydration = RehydrationService(self.storage)
        self.retention = RetentionService(self.settings, self.storage)
        self.documents = DocumentSanitizer(self.pii, image_pipeline=self.image_pipeline)
        self.audit = get_audit_logger()
        self.claim_schema = self._load_schema()

    def _load_schema(self) -> dict[str, Any]:
        if self.settings.claim_schema_path and Path(self.settings.claim_schema_path).exists():
            return json.loads(Path(self.settings.claim_schema_path).read_text(encoding="utf-8"))
        return DEFAULT_CLAIM_SCHEMA

    def _schema_pii_fields(self) -> dict[str, str]:
        props = self.claim_schema.get("properties", {})
        out: dict[str, str] = {}
        for name, meta in props.items():
            if isinstance(meta, dict) and meta.get("pii"):
                out[name.lower()] = str(meta.get("entity", "PERSON"))
        return out

    def _get(self, session_id: str) -> ClaimSession:
        session = self.storage.load_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def _set_state(self, session: ClaimSession, target: ClaimState) -> None:
        session.state = transition(session.state, target)
        session.touch()

    def create_session(self) -> ClaimSession:
        session_id = generate_session_id()
        session = ClaimSession(session_id=session_id, state=ClaimState.RECEIVED)
        self.storage.ensure_session_dirs(session_id)
        self.storage.save_session(session)
        self.audit.log("SESSION_CREATED", session_id=session_id)
        return session

    def add_claim_record(self, session_id: str, claim: dict[str, Any]) -> SessionInput:
        session = self._get(session_id)
        input_id = f"CLAIM_{uuid.uuid4().hex[:8]}"
        rel = f"claim/{input_id}.json"
        self.storage.write_raw_json(session_id, rel, claim)
        inp = SessionInput(
            input_id=input_id,
            kind=InputKind.CLAIM_RECORD,
            original_filename="claim.json",
            content_type="application/json",
            storage_path=rel,
        )
        session.inputs.append(inp)
        session.touch()
        self.storage.save_session(session)
        self.audit.log("INPUT_RECEIVED", session_id=session_id, kind="claim_record", input_id=input_id)
        return inp

    def add_image(
        self,
        session_id: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> SessionInput:
        session = self._get(session_id)
        ext = Path(filename).suffix.lower() or ".jpg"
        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {ext}")
        input_id = f"IMG_{uuid.uuid4().hex[:8]}"
        rel = f"images/{input_id}{ext}"
        self.storage.write_raw_bytes(session_id, rel, data)
        inp = SessionInput(
            input_id=input_id,
            kind=InputKind.IMAGE,
            original_filename=filename,
            content_type=content_type or "image/jpeg",
            storage_path=rel,
        )
        session.inputs.append(inp)
        session.touch()
        self.storage.save_session(session)
        self.audit.log("INPUT_RECEIVED", session_id=session_id, kind="image", input_id=input_id)
        return inp

    def add_document(
        self,
        session_id: str,
        filename: str,
        data: bytes,
        document_type: str = "DOCUMENT",
        content_type: str | None = None,
    ) -> SessionInput:
        session = self._get(session_id)
        input_id = f"DOC_{uuid.uuid4().hex[:8]}"
        rel = f"documents/{input_id}_{filename}"
        self.storage.write_raw_bytes(session_id, rel, data)
        # Sanitised copy is produced during sanitize() after Presidio redaction.
        # Do not write unsanitised binaries into sanitised/.
        inp = SessionInput(
            input_id=input_id,
            kind=InputKind.DOCUMENT,
            original_filename=filename,
            content_type=content_type or "application/pdf",
            storage_path=rel,
            metadata={"document_type": document_type},
        )
        session.inputs.append(inp)
        session.touch()
        self.storage.save_session(session)
        self.audit.log("INPUT_RECEIVED", session_id=session_id, kind="document", input_id=input_id)
        return inp

    def sanitize(self, session_id: str) -> ClaimSession:
        session = self._get(session_id)
        try:
            # Allow re-sanitize after earlier runs so plate/face redaction fixes can be applied
            reentrant = {
                ClaimState.PROCESSING,
                ClaimState.SANITIZATION_ERROR,
                ClaimState.SANITIZED,
                ClaimState.VALIDATED,
                ClaimState.VALIDATION_ERROR,
                ClaimState.READY_FOR_LLM,
            }
            if session.state == ClaimState.RECEIVED:
                self._set_state(session, ClaimState.PROCESSING)
            elif session.state in reentrant:
                self._set_state(session, ClaimState.PROCESSING)
            else:
                raise InvalidStateTransition(session.state, ClaimState.PROCESSING)

            registry = PlaceholderRegistry(self.storage.load_mapping(session_id))
            image_results = []
            sanitised_texts: dict[str, str] = {}

            # Process images
            for inp in session.inputs:
                if inp.kind != InputKind.IMAGE:
                    continue
                raw_bytes = self.storage.read_raw_bytes(session_id, inp.storage_path)
                # Decrypt to temp working file under raw (plaintext temp for CV tooling)
                work_dir = self.storage.raw_dir(session_id) / "_work"
                work_dir.mkdir(parents=True, exist_ok=True)
                src = work_dir / Path(inp.storage_path).name
                src.write_bytes(raw_bytes)

                out_img = self.storage.sanitised_dir(session_id) / "images" / Path(inp.storage_path).name
                out_ocr = self.storage.sanitised_dir(session_id) / "ocr" / f"{inp.input_id}.txt"
                result, ocr_text = self.image_pipeline.process(
                    session_id=session_id,
                    input_id=inp.input_id,
                    source_path=src,
                    output_image_path=out_img,
                    ocr_output_path=out_ocr,
                    registry=registry,
                )
                image_results.append(result)
                if ocr_text:
                    sanitised_texts[inp.input_id] = ocr_text
                # Remove plaintext work copy
                try:
                    src.unlink(missing_ok=True)
                except OSError:
                    pass

            # Process claim records
            sanitised_claim: dict[str, Any] = {}
            total_entities = 0
            for inp in session.inputs:
                if inp.kind != InputKind.CLAIM_RECORD:
                    continue
                raw = self.storage.read_raw_bytes(session_id, inp.storage_path)
                claim = json.loads(raw.decode("utf-8"))
                sanitised_claim, count = self.pii.sanitize_claim_record(
                    claim,
                    registry,
                    self._schema_pii_fields(),
                )
                total_entities += count
                self.audit.log(
                    "PII_DETECTED",
                    session_id=session_id,
                    entity_count=count,
                    input_id=inp.input_id,
                )

            # Process documents (extract → Presidio → sanitised text only; no raw binary)
            for inp in session.inputs:
                if inp.kind != InputKind.DOCUMENT:
                    continue
                raw = self.storage.read_raw_bytes(session_id, inp.storage_path)
                result = self.documents.sanitize(
                    inp.original_filename,
                    raw,
                    registry,
                    self._schema_pii_fields(),
                    session_id=session_id,
                    input_id=inp.input_id,
                    image_pipeline=self.image_pipeline,
                )
                sanitised_rel = f"documents/{result['sanitised_filename']}"
                self.storage.write_sanitised_bytes(
                    session_id, sanitised_rel, result["sanitised_bytes"]
                )
                for extra in result.get("extra_files") or []:
                    extra_rel = f"documents/{extra['filename']}"
                    self.storage.write_sanitised_bytes(session_id, extra_rel, extra["bytes"])
                for stale in result.get("remove_filenames") or []:
                    stale_path = self.storage.sanitised_dir(session_id) / "documents" / stale
                    stale_path.unlink(missing_ok=True)
                inp.metadata = {
                    **(inp.metadata or {}),
                    "sanitised_path": sanitised_rel,
                    "sanitised_files": [result["sanitised_filename"]]
                    + [e["filename"] for e in (result.get("extra_files") or [])],
                    "binary_withheld": result["binary_withheld"],
                    "document_entities": result["entities"],
                    "image_pages_redacted": result.get("image_pages_redacted", 0),
                    "text_pages_redacted": result.get("text_pages_redacted", 0),
                }
                total_entities += int(result["entities"])
                if result.get("sanitised_text"):
                    sanitised_texts[inp.input_id] = result["sanitised_text"]
                self.audit.log(
                    "DOCUMENT_SANITISED",
                    session_id=session_id,
                    input_id=inp.input_id,
                    entity_count=result["entities"],
                    binary_withheld=result["binary_withheld"],
                    image_pages_redacted=result.get("image_pages_redacted", 0),
                )

            self.storage.write_sanitised_json(session_id, "claim.json", sanitised_claim)
            # Always emit a viewable redacted claim PDF for the Output UI
            claim_pdf_name = "claim.sanitised.pdf"
            claim_pdf_body = build_redacted_pdf(
                json.dumps(sanitised_claim, indent=2) if sanitised_claim else "(no claim record)",
                title="Sanitised claim record",
            )
            self.storage.write_sanitised_bytes(
                session_id, f"documents/{claim_pdf_name}", claim_pdf_body
            )
            self.storage.save_mapping(session_id, registry.mapping)
            for ph in registry.mapping:
                self.audit.log("PLACEHOLDER_CREATED", session_id=session_id, placeholder=ph)

            session.image_results = image_results
            session.text_result = TextSanitizationResult(
                entities_detected=total_entities,
                placeholders_created=len(registry.mapping),
                sanitised_claim=sanitised_claim,
                sanitised_texts=sanitised_texts,
            )
            self._set_state(session, ClaimState.SANITIZED)
            session.error_message = None
            self.storage.save_session(session)
            self.audit.log("SANITIZATION_COMPLETED", session_id=session_id)
            return session
        except InvalidStateTransition:
            raise
        except Exception as exc:  # noqa: BLE001
            session.error_message = str(exc)
            try:
                session.state = transition(session.state, ClaimState.SANITIZATION_ERROR)
            except InvalidStateTransition:
                session.state = ClaimState.SANITIZATION_ERROR
            session.touch()
            self.storage.save_session(session)
            raise

    def validate(self, session_id: str) -> ClaimSession:
        session = self._get(session_id)
        if session.state not in {ClaimState.SANITIZED, ClaimState.VALIDATION_ERROR}:
            raise InvalidStateTransition(session.state, ClaimState.VALIDATED)
        report = self.validator.validate(session)
        session.validation = report
        if report.passed:
            self._set_state(session, ClaimState.VALIDATED)
        else:
            self._set_state(session, ClaimState.VALIDATION_ERROR)
        self.storage.save_session(session)
        return session

    def prepare(self, session_id: str) -> ClaimSession:
        session = self._get(session_id)
        if session.state != ClaimState.VALIDATED:
            raise InvalidStateTransition(session.state, ClaimState.READY_FOR_LLM)
        # Re-check privacy gate
        report = self.validator.validate(session)
        session.validation = report
        if not report.passed:
            self._set_state(session, ClaimState.VALIDATION_ERROR)
            self.storage.save_session(session)
            return session
        self.package_builder.build(session)
        self.payload_builder.build(session)
        self._set_state(session, ClaimState.READY_FOR_LLM)
        self.storage.save_session(session)
        return session

    def get_llm_payload(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        if session.state != ClaimState.READY_FOR_LLM and session.state not in {
            ClaimState.REHYDRATED,
            ClaimState.REHYDRATION_REQUESTED,
        }:
            raise InvalidStateTransition(session.state, ClaimState.READY_FOR_LLM)
        payload = self.storage.read_llm_payload(session_id)
        if payload is None:
            raise FileNotFoundError("LLM payload not found")
        # Safety: ensure mapping keys' values never appear
        mapping = self.storage.load_mapping(session_id)
        blob = json.dumps(payload)
        for original in mapping.values():
            if original and original in blob:
                raise RuntimeError("Raw PII detected in LLM payload — refusing to return")
        return payload

    def rehydrate(
        self,
        session_id: str,
        content: str | dict[str, Any],
        policy: RehydrationPolicy = RehydrationPolicy.FULL,
        allowed_entities: list[str] | None = None,
    ) -> tuple[ClaimSession, dict[str, Any]]:
        session = self._get(session_id)
        if session.state not in {
            ClaimState.READY_FOR_LLM,
            ClaimState.REHYDRATED,
            ClaimState.REHYDRATION_ERROR,
        }:
            raise InvalidStateTransition(session.state, ClaimState.REHYDRATION_REQUESTED)
        self._set_state(session, ClaimState.REHYDRATION_REQUESTED)
        try:
            self.retention.assert_mapping_valid(session_id)
            result = self.rehydration.rehydrate(session_id, content, policy, allowed_entities)
            self._set_state(session, ClaimState.REHYDRATED)
            self.storage.save_session(session)
            return session, result
        except MappingExpiredError:
            session.error_message = "Placeholder mapping expired"
            self._set_state(session, ClaimState.REHYDRATION_ERROR)
            self.storage.save_session(session)
            raise
        except Exception:
            self._set_state(session, ClaimState.REHYDRATION_ERROR)
            self.storage.save_session(session)
            raise
