"""
Call 1 — Damage Description: classify claim images into damage_type and
severity, images only, no claimant text in the prompt.

One multimodal request per claim, all images sent together (not one call
per image), so the model can reason across angles instead of judging each
photo in isolation.
"""

from __future__ import annotations

import asyncio
import base64
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDamageAssessment, ClaimDocument
from app.connectors.foundry import get_gpt_client, get_gpt_deployment
from app.connectors.storage import download_stored_blob
from app.services.audit_log_service import get_or_create_decision, log_stage

MAX_IMAGES = 6
IMAGE_FILE_TYPES = ("image/jpeg", "image/png")

class DamageType(str, Enum):
    STORM = "storm"
    FIRE = "fire"
    FLOOD = "flood"
    CYCLONE = "cyclone"
    OTHER = "other"

class DamageSeverity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    NONE = "none"

class DamageAssessment(BaseModel):
    # Order: gate -> observe -> reason -> classify -> self-rate. The model
    # generates left to right, so each field is available as context for the next

    images_assessable: bool = Field(
        description="True only if the images are clear, relevant and sufficient to assess the damage"
    )
    damage_description: str = Field(
        description="What is visually observed across the images."
    )
    reasoning: str = Field(
        description="Reasoning linkning the visual evidence to the classification below."
    )
    damage_type: DamageType
    percent_area_affected: float = Field(
        ge=0, le=100,
        description="Best visual estimate of how much of the damaged surface is affected overall, "
        "0-100. For a vehicle: roughly what percentage of the exterior body/panels shown have "
        "visible damage. For a property: roughly what percentage of the visible room(s)/structure "
        "shown are affected. 0 if no damage is visible.",
    )
    severity: DamageSeverity = Field(
        description="Your own direct severity judgement, using the rubric below - kept alongside "
        "percent_area_affected (not derived from it) so the two can be compared."
    )

_SEVERITY_RUBRIC = {
    "motor": """Motor severity rubric:
    - minor: cosmetic damage only (scratches, small dents, a chipped/cracked windscreen); no
      structural or mechanical component affected; vehicle still driveable.
    - moderate: one or more body panels or parts need repair/replacement, but no structural
      (chassis/frame) or safety-critical mechanical damage; vehicle may still be driveable.
    - severe: structural or safety-critical mechanical damage (frame, engine, airbags deployed,
      steering), vehicle not driveable, or damage spread across most of the vehicle.""",
    "property": """Property severity rubric:
    - minor: isolated, surface-level damage confined to a small area or single fixture (e.g. a
      cracked tile, a small water stain); no structural impact.
    - moderate: damage affecting one or more full rooms or a significant exterior element (e.g. a
      roof section, an exterior wall), but the property remains structurally sound and habitable.
    - severe: significant structural damage, multiple rooms or the whole dwelling affected, or the
      property is not currently habitable.""",
}
_GENERIC_SEVERITY_RUBRIC = """Severity rubric (no product specified):
    - minor: isolated, cosmetic/surface-level damage, nothing structural.
    - moderate: multiple components/areas affected, but the structure/vehicle remains usable.
    - severe: structural damage, or damage so extensive the property/vehicle is unusable."""

_INSTRUCTIONS_TEMPLATE = """ You are assessing insurance claim photos. You are shown only the
    images below plus some submission metadata - no claimant statement. Judge only
    from what is visible.

    First decide whether the images are good enough to assess at all. Then describe
    the visible damage, explain your reasoning, and classify the damage type. Estimate
    percent_area_affected as a plain number, then use the rubric below to judge severity -
    the claimant-selected category, if given, is a weak hint only - do not defer to it.

    {rubric}
    """

class NoClaimImagesError(Exception):
    """The claim has no images to assess."""

# First-pass thresholds, not yet tuned against a labelled eval set - revisit
# once severity accuracy is actually measured against human-agreed labels.
_MINOR_MAX_PERCENT = 15
_MODERATE_MAX_PERCENT = 50

def _classify_severity_from_percent(percent_area_affected: float) -> DamageSeverity:
    """Deterministically buckets the model's own percent_area_affected estimate
    into a severity tier, same "model estimates a number, code decides the
    category"""

    if percent_area_affected <= 0:
        return DamageSeverity.NONE
    if percent_area_affected <= _MINOR_MAX_PERCENT:
        return DamageSeverity.MINOR
    if percent_area_affected <= _MODERATE_MAX_PERCENT:
        return DamageSeverity.MODERATE
    return DamageSeverity.SEVERE

async def assess_damage(claim_id: int, db: AsyncSession) -> ClaimDamageAssessment:
    """ Run CAll 1 for a claim and persist the result.

    Raises NoClaimImagesError if the claim has no images. Model or parse failures
    propagate to the caller and nothing is persisted, so the caller owns retry/escalation.
    An 'image_assessable=False' result IS persisted (valid verdict, not a failure)
    """
    claim = await db.get(Claim, claim_id)
    decision_stub = await get_or_create_decision(db, claim_id)

    result  = await db.execute(
        select(ClaimDocument)
        .where(
            ClaimDocument.claim_id == claim_id,
            ClaimDocument.file_type.in_(IMAGE_FILE_TYPES)
        )
        .order_by(ClaimDocument.upload_date, ClaimDocument.doc_id)
    )
    documents = result.scalars().all()
    if not documents:
        decision_stub.decision = "refer_to_assessor"
        decision_stub.reason_summary = f"claim_id={claim_id} has no images to assess."
        await db.commit()
        await log_stage(db, decision_stub.decision_id, "damage_description", decision_stub.reason_summary)
        raise NoClaimImagesError(f"Claim {claim_id} has no images to assess")

    selected = documents[:MAX_IMAGES]

    content: list[dict] = [{"type": "input_text", "text": _build_prompt(claim)}]
    for doc in selected:
        image_bytes = await download_stored_blob(doc.file_url)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{doc.file_type};base64,{b64}",
            }
        )
    parsed = await asyncio.to_thread(_call_model, content)
    derived_severity = _classify_severity_from_percent(parsed.percent_area_affected)

    assessment = ClaimDamageAssessment(
        claim_id=claim_id,
        images_assessable=parsed.images_assessable,
        damage_description=parsed.damage_description,
        reasoning=parsed.reasoning,
        damage_type=parsed.damage_type.value,
        # severity is the deterministic, percent-based classification 
        severity=derived_severity.value,
        model_severity=parsed.severity.value,
        percent_area_affected=parsed.percent_area_affected,
        images_available=len(documents),
        images_assessed=len(selected),
        model=get_gpt_deployment(),
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    await log_stage(
        db, decision_stub.decision_id, "damage_description",
        f"images_assessable={parsed.images_assessable}; damage_type={parsed.damage_type.value}; severity={derived_severity.value}",
        input_payload={"images_available": len(documents), "images_assessed": len(selected)},
        output_payload={
            "damage_description": parsed.damage_description,
            "damage_type": parsed.damage_type.value,
            "severity": derived_severity.value,
            "model_severity": parsed.severity.value,
            "percent_area_affected": parsed.percent_area_affected,
            "images_assessable": parsed.images_assessable,
            "reasoning": parsed.reasoning,
        },
        model_name=get_gpt_deployment(),
    )

    return assessment


async def get_latest_assessment(claim_id: int, db: AsyncSession) -> ClaimDamageAssessment | None:
    """Return the most recent Call 1 result for a claim, or None if there isn't one."""
    result = await db.execute(
        select(ClaimDamageAssessment)
        .where(ClaimDamageAssessment.claim_id == claim_id)
        .order_by(ClaimDamageAssessment.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _call_model(content: list[dict]) -> DamageAssessment:
    """Blocking Foundry call, run in a worker thread by assess_damage().

    responses.parse(text_format=...) is the OpenAI Responses API structured-
    output pattern 
    """
    response = get_gpt_client().responses.parse(
        model=get_gpt_deployment(),
        input=[{"role": "user", "content": content}],
        text_format=DamageAssessment,
    )
    return response.output_parsed
    
def _build_prompt(claim: Claim) -> str:
    rubric = _SEVERITY_RUBRIC.get(claim.insurance_type, _GENERIC_SEVERITY_RUBRIC)
    instructions = _INSTRUCTIONS_TEMPLATE.format(rubric=rubric)
    lines = [instructions, "", f"Submission date/time: {claim.submission_date}"]
    if claim.claim_type:
        lines.append(f"Claimant-selected category (weak hint): {claim.claim_type}")
    return "\n".join(lines)
