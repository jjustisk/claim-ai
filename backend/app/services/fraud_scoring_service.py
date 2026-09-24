"""
Claim history and frequency fraud sub-scores which serves as a signal for the LLM.

Two scores return a structured breakdown so
the raw counts/rates of claims and rejections can be used to get a combined score and can be logged
to the audit trail and shown to an assessor.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimStatus
from app.services.image_similarity_service import image_similarity_score

W_CLAIM_COUNT = 0.35
W_REJECTION_RATE = 0.65
W_HISTORY = 0.35
W_FREQUENCY = 0.30
W_IMAGE_SIMILARITY = 0.35

_TERMINAL_STATUSES = (
    ClaimStatus.APPROVED.value,
    ClaimStatus.REJECTED.value,
    ClaimStatus.CLOSED.value,
)


async def _claim_count_last_12_months(
    db: AsyncSession, customer_id: int, as_of: datetime, exclude_claim_id: int
) -> int:
    """Counts the customer's non-draft claims in the trailing 12 months, excluding one claim."""
    cutoff = as_of - timedelta(days=365)
    result = await db.execute(
        select(func.count(Claim.claim_id)).where(
            Claim.customer_id == customer_id,
            Claim.claim_id != exclude_claim_id,
            Claim.status != ClaimStatus.DRAFT.value,
            Claim.submission_date >= cutoff,
            Claim.submission_date <= as_of,
        )
    )
    return result.scalar_one()


def _claim_count_threshold(count: int) -> float:
    """Maps a claim count to its risk score threshold."""
    if count <= 1:
        return 0.0
    if count <= 3:
        return 0.3
    if count <= 5:
        return 0.6
    return 1.0


async def _rejection_rate(db: AsyncSession, customer_id: int, exclude_claim_id: int) -> float:
    """Returns the customer's rejection rate across their resolved claims, excluding one claim."""
    result = await db.execute(
        select(
            func.count(Claim.claim_id),
            func.count(Claim.claim_id).filter(Claim.status == ClaimStatus.REJECTED.value),
        ).where(
            Claim.customer_id == customer_id,
            Claim.claim_id != exclude_claim_id,
            Claim.status.in_(_TERMINAL_STATUSES),
        )
    )
    total, rejected = result.one()
    return 0.0 if total == 0 else rejected / total


def _rejection_rate_threshold(rate: float) -> float:
    """Maps a rejection rate to its risk score threshold."""
    if rate <= 0.10:
        return 0.0
    if rate <= 0.30:
        return 0.3
    if rate <= 0.60:
        return 0.6
    return 1.0


async def _last_claim_date(
    db: AsyncSession, customer_id: int, exclude_claim_id: int, before: datetime
) -> datetime | None:
    """Returns the customer's most recent prior claim submission date, if any."""
    result = await db.execute(
        select(func.max(Claim.submission_date)).where(
            Claim.customer_id == customer_id,
            Claim.claim_id != exclude_claim_id,
            Claim.status != ClaimStatus.DRAFT.value,
            Claim.submission_date < before,
        )
    )
    return result.scalar_one_or_none()


def _frequency_threshold(days_since: int | None) -> float:
    """Maps days-since-last-claim to its risk score threshold."""
    if days_since is None:
        return 0.0
    if days_since < 30:
        return 1.0
    if days_since < 90:
        return 0.6
    if days_since < 180:
        return 0.3
    if days_since <= 365:
        return 0.1
    return 0.0


async def history_score(db: AsyncSession, customer_id: int, claim: Claim) -> dict:
    """Computes the customer's claim-history fraud score from claim count and rejection rate."""
    count = await _claim_count_last_12_months(db, customer_id, claim.submission_date, claim.claim_id)
    rate = await _rejection_rate(db, customer_id, claim.claim_id)
    count_score = _claim_count_threshold(count)
    rate_score = _rejection_rate_threshold(rate)
    return {
        "claim_count": count,
        "rejection_rate": rate,
        "claim_count_score": count_score,
        "rejection_rate_score": rate_score,
        "history_score": W_CLAIM_COUNT * count_score + W_REJECTION_RATE * rate_score,
    }


async def frequency_score(db: AsyncSession, customer_id: int, claim: Claim) -> dict:
    """Computes the customer's claim-frequency fraud score from days since their last claim."""
    last_date = await _last_claim_date(db, customer_id, claim.claim_id, claim.submission_date)
    days_since = (claim.submission_date - last_date).days if last_date else None
    return {
        "days_since_last_claim": days_since,
        "frequency_score": _frequency_threshold(days_since),
    }


async def compute_fraud_flag(db: AsyncSession, customer_id: int, claim: Claim) -> dict:
    """Computes the combined fraud flag from history, frequency, and image similarity."""
    history = await history_score(db, customer_id, claim)
    frequency = await frequency_score(db, customer_id, claim)
    image_similarity = await image_similarity_score(db, claim.claim_id)
    fraud_flag = (
        W_HISTORY * history["history_score"]
        + W_FREQUENCY * frequency["frequency_score"]
        + W_IMAGE_SIMILARITY * image_similarity["image_similarity_score"]
    )
    return {
        "history": history,
        "frequency": frequency,
        "image_similarity": image_similarity,
        "fraud_flag": fraud_flag,
    }
