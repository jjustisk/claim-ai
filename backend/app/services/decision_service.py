"""Generation — Call A: composite-scored coverage decision from Call 1,
Call 2, and CRAG-retrieved clauses. No second model yet (Claude Validation
deferred - region-limited); the composite formula's claude_agreement term
is dropped and the remaining weights rescaled to still sum to 1.0.
"""

from __future__ import annotations

import asyncio
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import AIDecision, Claim, ClaimDamageAssessment, Policy
from app.connectors.foundry import get_gpt_client, get_gpt_deployment
from app.services.audit_log_service import get_or_create_decision, log_stage
from app.services.consistency_check_service import ConsistencyResult, check_consistency
from app.services.damage_description_services import get_latest_assessment
from app.services.policy_retrieval_service import retrieve_clauses

FRAUD_STUB = 0.0
SEED = 42

W_CONSISTENCY = 0.375
W_RAG = 0.3125
W_FRAUD = 0.3125

DECISION_REFER = "refer_to_assessor"
REFERRED_CUSTOMER_MESSAGE = (
    "Your claim is currently being reviewed by one of our assessors. "
    "We'll be in touch as soon as a decision has been made. Thank you for your patience."
)

class CoverageDecision(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    EXCLUDED = "excluded"

class Decision(BaseModel):
    # Order: reason -> citation -> the model's own calibrated signal ratings
    # -> coverage judgment -> customer-facing rephrasing, generated last
    # since it summarizes everything decided above it.

    reasoning: str = Field(description="Reasoning citing the specific clause section_ref(s) relied on")
    cited_clause_ref: str = Field(description="The section_ref of the clause primarily relied on")
    adjusted_consistency: float = Field(ge=0.0, le=1.0)
    adjusted_rag: float = Field(ge=0.0, le=1.0)
    coverage_decision: CoverageDecision
    customer_explanation: str = Field(
        description="Plain-language explanation of the decision for the claimant - "
        "clear and respectful, may reference the relevant policy section, no internal jargon"
    )

class NoDamageAssessmentError(Exception):
    """The claim has no Call 1 assessment to compare against yet."""

async def generate_decision(claim_id: int, db: AsyncSession) -> AIDecision:
    claim = await db.get(Claim, claim_id)
    policy = await db.get(Policy, claim.policy_id)

    assessment = await get_latest_assessment(claim_id, db)
    if assessment is None:
        raise NoDamageAssessmentError(f"claim_id={claim_id} has no damage assessment yet.")

    if not assessment.images_assessable:
        return await _refer(db, claim_id, "Call 1 could not assess the images.")

    if policy.product_id is None:
        return await _refer(db, claim_id, "Policy has no classified product: cannot retrieve clauses")

    consistency, retrieval = await asyncio.gather(
        check_consistency(claim_id, db),
        asyncio.to_thread(retrieve_clauses, assessment.damage_description, product_id=policy.product_id),
    )

    prompt = _build_prompt(assessment, retrieval, consistency, FRAUD_STUB)
    parsed = await asyncio.to_thread(_call_model, prompt)

    composite = _composite_score(parsed.adjusted_consistency, parsed.adjusted_rag, FRAUD_STUB)
    band = _band(composite)
    decision = DECISION_REFER if band =="low" else parsed.coverage_decision.value
    customer_explanation = REFERRED_CUSTOMER_MESSAGE if band == "low" else parsed.customer_explanation

    memo = _build_memo(
        claim, assessment, decision=decision, reasoning=parsed.reasoning, retrieval=retrieval,
        consistency=consistency, composite=composite, band=band,
        )

    record = await _persist(
        db, claim_id, decision, parsed.reasoning, memo, customer_explanation, confidence=composite,
    )

    await log_stage(
        db, record.decision_id, "generation",
        f"Composite score {composite:.1f} ({band}); coverage_decision={parsed.coverage_decision.value}",
        input_payload={
            "damage_type": assessment.damage_type,
            "severity": assessment.severity,
            "retrieval_action": retrieval["action"],
            "consistency_flag": consistency.consistency_flag,
        },
        output_payload={
            "adjusted_consistency": parsed.adjusted_consistency,
            "adjusted_rag": parsed.adjusted_rag,
            "coverage_decision": parsed.coverage_decision.value,
            "cited_clause_ref": parsed.cited_clause_ref,
            "reasoning": parsed.reasoning,
        },
        model_name=get_gpt_deployment(),
    )
    return record

def _composite_score(adjusted_consistency: float, adjusted_rag: float, adjusted_fraud: float) -> float:
    return (
        W_CONSISTENCY * adjusted_consistency
        + W_RAG * adjusted_rag
        + W_FRAUD * (1 - adjusted_fraud)
    ) * 100.0

def _band(composite: float) -> str:
    if composite >= 85:
        return "high"
    if composite >= 70:
        return "moderate"
    return "low"

async def _refer(db: AsyncSession, claim_id: int, reason: str) -> AIDecision:
    record = await _persist(
        db, claim_id, DECISION_REFER, reason, reason, REFERRED_CUSTOMER_MESSAGE, confidence=None,
    )
    await log_stage(db, record.decision_id, "generation", reason)
    return record


async def _persist(
    db: AsyncSession, claim_id: int, decision: str, reason_summary: str, memo: str,
    customer_explanation: str, confidence: float | None = None,
) -> AIDecision:
    record = await get_or_create_decision(db, claim_id)
    record.decision = decision
    record.reason_summary = reason_summary
    record.assessor_memo = memo
    record.customer_explanation = customer_explanation
    record.confidence_score = confidence
    await db.commit()
    await db.refresh(record)
    return record


def _call_model(prompt: str) -> Decision:
    response = get_gpt_client().responses.parse(
        model=get_gpt_deployment(),
        input=[{"role": "user", "content": prompt}],
        text_format=Decision,
        # Neither temperature nor seed are supported for gpt-5.5 on the
        # Responses API (confirmed live - both raise 400 BadRequestError).
        # This is a reasoning-tier model; sampling isn't exposed as a
        # tunable parameter the way it is on gpt-4o-class models. The doc's
        # determinism strategy (decision 9) needs revisiting for this model.
    )
    return response.output_parsed

def _build_prompt(assessment: ClaimDamageAssessment, retrieval: dict, consistency: ConsistencyResult, fraud_flag: float) -> str:
    clauses = "\n".join(
        f"[{m['metadata'].get('section_ref')}] {m['text']}" for m in retrieval["matches"]
    ) or "(none)"
    exclusions = "\n".join(
        f"[{m['metadata'].get('section_ref')}] {m['text']}" for m in retrieval["linked_exclusions"]
    ) or "(none)"
    definitions = "\n".join(f"{d['term']}: {d['meaning']}" for d in retrieval["linked_definitions"]) or "(none)"
    discrepancies = "\n".join(f"  - {d}" for d in consistency.discrepancies) or "  (none)"

    return f"""You are deciding whether an insurance claim is covered, based on the
    evidence below. Cite the section_ref of every clause you rely on.

    Also rate, 0-1, your own calibrated view of (a) how consistent the
    claimant's account is with the evidence, and (b) how well the retrieved
    clause(s) actually support your classification.

    Finally, write a plain-language explanation of the decision suitable to
    send directly to the claimant - clear and respectful, no internal jargon
    or scoring language, though it may reference the relevant policy section.

    Damage assessment (from claim images):
    - description: {assessment.damage_description}
    - damage_type: {assessment.damage_type}
    - severity: {assessment.severity}

    Retrieval confidence: {retrieval['action']}
    Retrieved coverage clause(s):
    {clauses}

    Linked exclusions:
    {exclusions}

    Relevant definitions:
    {definitions}

    Consistency check: flag={consistency.consistency_flag}
    Discrepancies noted:
    {discrepancies}

    Fraud risk signal (0-1, stub until Stage 2 is built): {fraud_flag}
    """

def _build_memo(
    claim: Claim, assessment: ClaimDamageAssessment, decision: str, reasoning: str,
    retrieval: dict, consistency: ConsistencyResult, composite: float | None, band: str | None,
) -> str:
    sections = [
        f"Claim {claim.claim_reference} — Decision: {decision}",
        f"Composite confidence: {composite:.1f} ({band})" if composite is not None else "Composite confidence: n/a (referred before scoring)",
        "",
        "Damage assessment (Call 1):",
        f"  {assessment.damage_description}",
        f"  Type: {assessment.damage_type} | Severity: {assessment.severity}",
    ]
    clauses = "\n".join(
        f"  [{m['metadata'].get('section_ref')}] {m['text']}" for m in retrieval["matches"]
    ) or "  (none)"
    sections += ["", "Retrieved policy clause(s):", clauses]
    discrepancies = "\n".join(f"  - {d}" for d in consistency.discrepancies) or "  (none)"
    sections += ["", f"Consistency check: flag={consistency.consistency_flag}", discrepancies]
    sections += ["", "Decision reasoning:", f"  {reasoning}"]
    return "\n".join(sections)





