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


class ClaimSubmitOut(BaseModel):
    claim_id: int
    claim_reference: str
    status: str
    files_uploaded: int


class ClaimFormOptions(BaseModel):
    claim_types: list[dict[str, str]]


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
