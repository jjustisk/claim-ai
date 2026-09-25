"""API request/response schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.session import (
    ImageProcessingResult,
    TextSanitizationResult,
    ValidationReport,
)
from app.models.states import ClaimState


class CreateClaimResponse(BaseModel):
    session_id: str
    state: ClaimState


class UploadInputsResponse(BaseModel):
    session_id: str
    state: ClaimState
    received_inputs: list[dict[str, Any]]


class SanitizeResponse(BaseModel):
    session_id: str
    state: ClaimState
    image_results: list[ImageProcessingResult]
    text_result: TextSanitizationResult | None = None
    error_message: str | None = None


class ValidateResponse(BaseModel):
    session_id: str
    state: ClaimState
    validation: ValidationReport


class PrepareResponse(BaseModel):
    session_id: str
    state: ClaimState
    package_path: str | None = None
    llm_payload_path: str | None = None


class RehydrationPolicy(str, Enum):
    FULL = "FULL"
    LIMITED = "LIMITED"
    NONE = "NONE"


class RehydrateRequest(BaseModel):
    content: str | dict[str, Any]
    rehydration_policy: RehydrationPolicy = RehydrationPolicy.FULL
    allowed_entities: list[str] = Field(default_factory=list)


class RehydrateResponse(BaseModel):
    session_id: str
    state: ClaimState
    status: str
    rehydrated: str | dict[str, Any] | None = None
    unknown_placeholders: list[str] = Field(default_factory=list)
    policy: RehydrationPolicy
