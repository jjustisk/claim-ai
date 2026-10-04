"""Orchestration: runs the full decision pipeline for a claim.

Input form -> PII reduction -> Call 1 (VLM) -> Generation (Call 2, CRAG,
composite score, memo). AI stages only consume PII-reduced evidence.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.api.schemas.models import AIDecision
from app.services.audit_log_service import get_or_create_decision, log_stage
from app.services.claim_pii_service import (
    PiiNotReadyError,
    PiiReductionError,
    ensure_claim_ready_for_ai,
    run_pii_reduction_for_claim,
)
from app.services.damage_description_services import (
    NoClaimImagesError,
    NoSanitisedImagesError,
    assess_damage,
)
from app.services.decision_service import generate_decision


async def run_decision_pipeline(claim_id: int, db: AsyncSession) -> AIDecision | None:
    """PII reduction, then Call 1, then Generation. Returns None if Call 1
    couldn't assess the images - the claim was already finalized as
    refer_to_assessor in that case, so there's nothing further to do.
    """
    try:
        await run_pii_reduction_for_claim(claim_id, db)
        await ensure_claim_ready_for_ai(claim_id, db)
    except (PiiReductionError, PiiNotReadyError) as exc:
        logger.error(
            "AI pipeline stopped claim_id=%s: PII not complete (%s). No model stages will run.",
            claim_id,
            exc,
        )
        decision_stub = await get_or_create_decision(db, claim_id)
        decision_stub.decision = "refer_to_assessor"
        decision_stub.reason_summary = f"PII reduction failed: {exc}"
        await db.commit()
        await log_stage(
            db,
            decision_stub.decision_id,
            "pii_reduction",
            decision_stub.reason_summary,
        )
        return None

    try:
        await assess_damage(claim_id, db)
    except (NoClaimImagesError, NoSanitisedImagesError):
        return None

    return await generate_decision(claim_id, db)
