"""Domain models for claim sessions and artefacts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.states import ClaimState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InputKind(str, Enum):
    CLAIM_RECORD = "claim_record"
    IMAGE = "image"
    DOCUMENT = "document"


class SessionInput(BaseModel):
    input_id: str
    kind: InputKind
    original_filename: str | None = None
    content_type: str | None = None
    storage_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=utc_now)


class ImageProcessingResult(BaseModel):
    input_id: str
    metadata_sanitised: bool = False
    faces_detected: int = 0
    faces_redacted: int = 0
    plates_detected: int = 0
    plates_redacted: int = 0
    ocr_completed: bool = False
    text_regions_redacted: int = 0
    sanitised_path: str | None = None
    ocr_path: str | None = None
    errors: list[str] = Field(default_factory=list)


class TextSanitizationResult(BaseModel):
    entities_detected: int = 0
    placeholders_created: int = 0
    sanitised_claim: dict[str, Any] = Field(default_factory=dict)
    sanitised_texts: dict[str, str] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)


class ClaimSession(BaseModel):
    session_id: str
    state: ClaimState = ClaimState.RECEIVED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    inputs: list[SessionInput] = Field(default_factory=list)
    image_results: list[ImageProcessingResult] = Field(default_factory=list)
    text_result: TextSanitizationResult | None = None
    validation: ValidationReport | None = None
    llm_payload_path: str | None = None
    package_path: str | None = None
    error_message: str | None = None
    audit_events: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utc_now()
