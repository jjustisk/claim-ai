"""JSON shapes the Vue app will call. SQLAlchemy tables live in models.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    role: str
    email: str
    name: str | None = None
    phone: str | None = None


class PolicyOut(BaseModel):
    policy_id: int
    policy_number: str
    coverage_type: str | None = None


class PolicyDocumentOut(BaseModel):
    pds_id: int
    version: str | None = None
    effective_date: datetime | None = None


class AssessorDecisionBriefOut(BaseModel):
    claim_id: int
    claim_reference: str | None = None
    status: str
    memo: str
    source: str | None = None
    preliminary_decision: str | None = None
    indicative_payment: str | None = None
    fraud_alert: bool | None = None
    fraud_score: float | None = None
    generated_at: str | None = None


class ClaimSubmitOut(BaseModel):
    claim_id: int
    claim_reference: str
    status: str
    files_uploaded: int
    pipeline_queued: bool | None = None
    pipeline_queue_position: int | None = None


class ClaimFormOptions(BaseModel):
    claim_types: list[dict[str, str]] = []
    insurance_types: list[dict[str, str]] = []
    property_claim_types: list[dict[str, str]] = []
    titles: list[dict[str, str]] = []
    states: list[dict[str, str]] = []
    contact_methods: list[dict[str, str]] = []
    motor_relationships: list[dict[str, str]] = []
    property_relationships: list[dict[str, str]] = []
    vehicle_types: list[dict[str, str]] = []
    vehicle_damage_areas: list[dict[str, str]] = []
    building_areas: list[dict[str, str]] = []
    contents_categories: list[dict[str, str]] = []

    model_config = {"extra": "allow"}


class ClaimCounts(BaseModel):
    all: int = 0
    submitted: int = 0
    under_review: int = 0
    approved: int = 0
    rejected: int = 0
    closed: int = 0

    model_config = {"extra": "allow"}


class ClaimListItem(BaseModel):
    claim_id: int
    claim_reference: str
    status: str
    submission_date: datetime | None = None
    priority_level: int | None = None
    fraud_risk_score: float | None = None
    cost: float | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    policy_number: str | None = None
    coverage_type: str | None = None

    model_config = {"extra": "allow"}


class ClaimListOut(BaseModel):
    counts: dict[str, int]
    items: list[dict[str, Any]]


class ReviewIn(BaseModel):
    outcome: str
    notes: str = Field(default="", max_length=4000)
    customer_explanation: str | None = Field(default=None, max_length=8000)
    suggested_payout: float | None = None
