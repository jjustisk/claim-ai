"""Call 2 — Consistency Check: compare Call 1's damage classification
against the claimant's own account of the incident. Text only, no images.

PII masking is deliberately skipped for now - sanitize_free_text() only
strips control chars/HTML/injection phrases, not PII. Revisit before this
handles real claimant data.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDamageAssessment
from app.connectors.foundry import get_gpt_client, get_mini_deployment
from app.services.audit_log_service import get_or_create_decision, log_stage
from app.services.damage_description_services import get_latest_assessment
from app.services.sanitization_service import sanitize_free_text


class ConsistencyResult(BaseModel):
    # Order: reason first, then the itemized mismatches it's based on, then
    # the single-number summary, generated last.
    reasoning: str = Field(description="Reasoning comparing the claimant's account against Call 1's classification.")
    discrepancies: list[str] = Field(description="Specific mismatches found; empty list if none.")
    consistency_flag: float = Field(ge=0.0, le=1.0, description="0 = highly inconsistent, 1 = fully consistent.")


_INSTRUCTIONS = """Compare an automated visual damage assessment against the
claimant's own written account of the same incident. Identify specific
discrepancies (e.g. claimant says flood, assessment says fire; claimant says
minor, assessment says severe). Some difference in wording is normal - only
flag discrepancies that would matter for coverage or an assessor's judgement.
"""


class NoDamageAssessmentError(Exception):
    """The claim has no Call 1 assessment to compare against yet."""


async def check_consistency(claim_id: int, db: AsyncSession) -> ConsistencyResult:
    claim = await db.get(Claim, claim_id)
    decision_stub = await get_or_create_decision(db, claim_id)

    assessment = await get_latest_assessment(claim_id, db)
    if assessment is None:
        raise NoDamageAssessmentError(f"claim_id={claim_id} has no damage assessment yet.")

    claimant_text = _build_claimant_text(claim)
    prompt = _build_prompt(assessment, claimant_text)

    parsed = await asyncio.to_thread(_call_model, prompt)

    await log_stage(
        db, decision_stub.decision_id, "consistency_check",
        f"consistency_flag={parsed.consistency_flag}",
        input_payload={"claimant_text_length": len(claimant_text)},
        output_payload={
            "consistency_flag": parsed.consistency_flag,
            "discrepancies": parsed.discrepancies,
            "reasoning": parsed.reasoning,
        },
        model_name=get_mini_deployment(),
    )

    return parsed


def _call_model(prompt: str) -> ConsistencyResult:
    # Mini, not the full GPT-5.5 tier used by Call 1/Generation - this is a
    # bounded comparison task (does the claimant's account match Call 1's
    # read), not open-ended reasoning, but it still needs real semantic
    # judgement (catching e.g. "flood" vs "gradual leak"), so nano is too
    # shallow here despite consistency_flag carrying the largest single
    # weight in Generation's composite score.
    response = get_gpt_client().responses.parse(
        model=get_mini_deployment(),
        input=[{"role": "user", "content": prompt}],
        text_format=ConsistencyResult,
    )
    return response.output_parsed


def _build_claimant_text(claim: Claim) -> str:
    parts = [claim.incident_description, claim.loss_description, claim.additional_comments]
    combined = "\n\n".join(sanitize_free_text(p) for p in parts if p)
    return combined or "(No claimant description provided.)"


def _build_prompt(assessment: ClaimDamageAssessment, claimant_text: str) -> str:
    return f"""{_INSTRUCTIONS}

Automated assessment (from claim images):
- damage_description: {assessment.damage_description}
- damage_type: {assessment.damage_type}
- severity: {assessment.severity}

Claimant's own account:
{claimant_text}
"""
