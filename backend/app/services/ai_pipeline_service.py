"""Orchestration: runs the full decision pipeline for a claim.

Call 1 (VLM damage assessment) -> Generation (which calls Call 2 and
CRAG retrieval internally, composite-scores, self-consistency-samples if
moderate, persists the decision, and finalizes the shared audit trail).

No new logic lives here - each stage already knows how to create/reuse the
shared "pending" ai_decision row and finalize itself on failure. This is
just the single caller that runs them in order for a given claim.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import AIDecision
from app.services.damage_description_services import NoClaimImagesError, assess_damage
from app.services.decision_service import generate_decision


async def run_decision_pipeline(claim_id: int, db: AsyncSession) -> AIDecision | None:
    """Runs Call 1 then Generation for one claim. Returns None if Call 1
    couldn't assess the images - the claim was already finalized as
    refer_to_assessor in that case, so there's nothing further to do.
    """
    try:
        await assess_damage(claim_id, db)
    except NoClaimImagesError:
        return None

    return await generate_decision(claim_id, db)
