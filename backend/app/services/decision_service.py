"""Generation — Call A: composite-scored coverage decision from Call 1,
Call 2, and CRAG-retrieved clauses. No second model yet (Claude Validation
deferred - region-limited); the composite formula's claude_agreement term
is dropped and the remaining weights rescaled to still sum to 1.0.

Self-consistency: only triggered for moderate-band results
(including those capped down from "high" by the retrieval flag below) -
sample a few more times, take the majority coverage_decision, average the
adjusted scores across whichever samples agree with it.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import AIDecision, Claim, ClaimDamageAssessment, Policy, Product
from app.connectors.foundry import get_gpt_client, get_gpt_deployment
from app.services.audit_log_service import get_or_create_decision, log_stage
from app.services.consistency_check_service import ConsistencyResult, check_consistency
from app.services.damage_description_services import get_latest_assessment
from app.services.fraud_scoring_service import compute_fraud_flag
from app.services.notification_service import event_for_decision, notify_customer
from app.services.policy_retrieval_service import retrieve_clauses
from app.services.policy_schedule_ingestion_service import parse_scenario_excesses

SELF_CONSISTENCY_SAMPLES = 3  # only for moderate-band results

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
    suggested_payout: float = Field(
        ge=0.0,
        description="Your own rough, non-binding repair/replacement cost estimate in dollars, "
        "before any excess or policy limit is applied. 0 if excluded or not estimable from the evidence.",
    )
    customer_explanation: str = Field(
        description="Plain-language explanation of the decision for the claimant - "
        "clear and respectful, may reference the relevant policy section, no internal jargon"
    )

class NoDamageAssessmentError(Exception):
    """The claim has no Call 1 assessment to compare against yet."""

# Cheap best-effort net for a claim filed against the wrong product's policy - only words unmistakably unique to one product (shared parts like roof/wall/window/door/ceiling are deliberately excluded to avoid false positives).
_MOTOR_KEYWORDS = {
    "vehicle", "car", "engine", "windscreen", "tyre", "tire", "bumper",
    "bonnet", "dashboard", "odometer", "exhaust", "collision",
}
_HOME_KEYWORDS = {
    "home", "house", "hallway", "fence", "kitchen", "bedroom", "bathroom",
    "attic", "basement", "plumbing", "backyard",
}

def _product_mismatch(text: str, insurance_type: str) -> bool:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    motor_hit, home_hit = bool(words & _MOTOR_KEYWORDS), bool(words & _HOME_KEYWORDS)
    return (insurance_type == "motor" and home_hit and not motor_hit) or (
        insurance_type == "property" and motor_hit and not home_hit
    )

# Generic words in an excess label (e.g. "excess" itself, "driver", "age")
# that would over-match almost any claim if left in - stripped before
# comparing a label's own words against the claim's context text.
_EXCESS_LABEL_STOPWORDS = {"excess", "driver", "age", "and", "or", "the"}

def _resolve_excess(excesses: dict[str, Decimal], context_text: str, flat_excess: Decimal | None) -> Decimal | None:
    """Matches the claim's context (damage type, cited clause, reasoning,
    incident description) against each scenario-specific excess label's own
    significant words - e.g. "glass excess" only matches if "glass" appears
    somewhere in the context. Falls back to "basic excess" from the
    schedule, then the policy's flat excess column, if nothing more
    specific matches. Driver-related excesses (young/inexperienced/
    undeclared driver) never match anything today - nothing in the claim
    captures driver age or declaration status, so those categories are
    unreachable until that data exists, not a bug in the matching itself.
    """
    context_words = set(re.findall(r"[a-z]+", context_text.lower()))
    for label, amount in excesses.items():
        if label == "basic excess":
            continue
        label_words = set(label.split()) - _EXCESS_LABEL_STOPWORDS
        if label_words & context_words:
            return amount
    return excesses.get("basic excess", flat_excess)


def _estimate_payout(
    parsed: Decision, policy: Policy, assessment: ClaimDamageAssessment, claim: Claim,
) -> tuple[Decimal | None, str | None]:
    """Deterministically clamps the model's own non-binding suggested_payout
    against this claim's actual applicable excess and the policy's max
    payout. Returns (final_payout, note_for_memo). Never trusts the model's
    raw number as-is - per the team's own decision, this is a fixed amount,
    not a range, and it's always bounded by real policy figures, never by
    the model's say-so alone.
    """
    if parsed.coverage_decision == CoverageDecision.EXCLUDED or parsed.suggested_payout <= 0:
        return None, None

    excesses = parse_scenario_excesses(policy.schedule_details)
    context_text = f"{assessment.damage_type} {parsed.cited_clause_ref} {parsed.reasoning} {claim.incident_description or ''}"
    applicable_excess = _resolve_excess(excesses, context_text, policy.excess)

    if applicable_excess is None and policy.max_payout is None:
        return None, "Payout not estimated: policy has no excess or max payout on file."

    raw = Decimal(str(parsed.suggested_payout))
    after_excess = raw - applicable_excess if applicable_excess is not None else raw
    if policy.max_payout is not None:
        after_excess = min(after_excess, policy.max_payout - (applicable_excess or Decimal(0)))
    final_payout = max(Decimal(0), after_excess)

    excess_label = next(
        (label for label, amount in excesses.items() if amount == applicable_excess and label != "basic excess"),
        "basic excess" if applicable_excess is not None else None,
    )
    note = (
        f"Suggested payout ${raw:,.2f}, less {excess_label or 'flat'} excess "
        f"${(applicable_excess or Decimal(0)):,.2f}, capped at policy max payout "
        f"where applicable: ${final_payout:,.2f}."
    )
    return final_payout, note


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

    # incident_description carries cause of loss (theft, racing, alcohol,
    # undisclosed mods - none of which are visible in a photo); damage_description
    # carries the visual specifics Call 1 actually saw. PDS clauses are organized
    # by cause, so retrieval needs both, not damage_description alone.
    retrieval_query = f"{claim.incident_description}\n{assessment.damage_description}"

    product = await db.get(Product, policy.product_id)
    if _product_mismatch(retrieval_query, product.insurance_type):
        return await _refer(db, claim_id, "Claim content doesn't match the policy's product type.")

    # compute_fraud_flag runs its own queries on `db` - kept sequential, not
    # gathered alongside check_consistency, since AsyncSession isn't safe
    # for concurrent use from two coroutines at once.
    fraud_result = await compute_fraud_flag(db, claim.customer_id, claim)
    fraud_flag = fraud_result["fraud_flag"]

    consistency, retrieval = await asyncio.gather(
        check_consistency(claim_id, db),
        asyncio.to_thread(retrieve_clauses, retrieval_query, product_id=policy.product_id),
    )

    prompt = _build_prompt(claim, assessment, retrieval, consistency, fraud_flag)
    parsed = await asyncio.to_thread(_call_model, prompt)

    composite = _composite_score(parsed.adjusted_consistency, parsed.adjusted_rag, fraud_flag)
    band = _band(composite)

    band, retrieval_capped = _cap_band_for_retrieval(band, retrieval)

    sc_info = {"samples": 1, "agreement": None}
    if band == "moderate":
        parsed, composite, band, sc_info = await _self_consistent_decision(prompt, parsed, fraud_flag)
        band, capped_again = _cap_band_for_retrieval(band, retrieval)
        retrieval_capped = retrieval_capped or capped_again

    decision = DECISION_REFER if band =="low" else parsed.coverage_decision.value
    customer_explanation = REFERRED_CUSTOMER_MESSAGE if band == "low" else parsed.customer_explanation

    payout, payout_note = (None, None) if band == "low" else _estimate_payout(parsed, policy, assessment, claim)

    memo = _build_memo(
        claim, assessment, decision=decision, reasoning=parsed.reasoning, retrieval=retrieval,
        consistency=consistency, composite=composite, band=band, retrieval_capped=retrieval_capped,
        sc_info=sc_info, payout_note=payout_note,
        )

    record = await _persist(
        db, claim_id, decision, parsed.reasoning, memo, customer_explanation, confidence=composite,
        payout=payout, fraud_flag=fraud_flag,
    )

    await log_stage(
        db, record.decision_id, "generation",
        f"Composite score {composite:.1f} ({band}); coverage_decision={parsed.coverage_decision.value}",
        input_payload={
            "damage_type": assessment.damage_type,
            "severity": assessment.severity,
            "retrieval_action": retrieval["action"],
            "retrieval_needs_human_review": retrieval["needs_human_review"],
            "consistency_flag": consistency.consistency_flag,
            "fraud_flag": fraud_flag,
            "fraud_history": fraud_result["history"],
            "fraud_frequency": fraud_result["frequency"],
            "fraud_image_similarity": fraud_result["image_similarity"],
        },
        output_payload={
            "adjusted_consistency": parsed.adjusted_consistency,
            "adjusted_rag": parsed.adjusted_rag,
            "coverage_decision": parsed.coverage_decision.value,
            "cited_clause_ref": parsed.cited_clause_ref,
            "reasoning": parsed.reasoning,
            "retrieval_capped": retrieval_capped,
            "self_consistency_samples": sc_info["samples"],
            "self_consistency_agreement": sc_info["agreement"],
            "suggested_payout_raw": parsed.suggested_payout,
            "payout": float(payout) if payout is not None else None,
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


def _cap_band_for_retrieval(band: str, retrieval: dict) -> tuple[str, bool]:
    if retrieval["needs_human_review"] and band == "high":
        return "moderate", True
    return band, False


async def _self_consistent_decision(
    prompt: str, first: Decision, fraud_flag: float
) -> tuple[Decision, float, str, dict]:
    """Only called on a moderate-band result. Samples SELF_CONSISTENCY_SAMPLES-1
    more times and takes the majority coverage_decision, averaging adjusted
    scores across whichever samples agree with it. The representative sample's
    text (reasoning/citation/customer_explanation) stands in for the group."""
    extra = await asyncio.gather(
        *[asyncio.to_thread(_call_model, prompt) for _ in range(SELF_CONSISTENCY_SAMPLES - 1)]
    )
    samples = [first, *extra]

    votes = Counter(s.coverage_decision for s in samples)
    majority_decision, majority_count = votes.most_common(1)[0]

    agreeing = [s for s in samples if s.coverage_decision == majority_decision]
    avg_consistency = sum(s.adjusted_consistency for s in agreeing) / len(agreeing)
    avg_rag = sum(s.adjusted_rag for s in agreeing) / len(agreeing)
    composite = _composite_score(avg_consistency, avg_rag, fraud_flag)
    band = _band(composite)

    representative = min(
        agreeing,
        key=lambda s: abs(s.adjusted_consistency - avg_consistency) + abs(s.adjusted_rag - avg_rag),
    )
    sc_info = {"samples": len(samples), "agreement": f"{majority_count}/{len(samples)}"}
    return representative, composite, band, sc_info


async def _refer(db: AsyncSession, claim_id: int, reason: str) -> AIDecision:
    record = await _persist(
        db, claim_id, DECISION_REFER, reason, reason, REFERRED_CUSTOMER_MESSAGE, confidence=None,
    )
    await log_stage(db, record.decision_id, "generation", reason)
    return record


async def _persist(
    db: AsyncSession, claim_id: int, decision: str, reason_summary: str, memo: str,
    customer_explanation: str, confidence: float | None = None, payout: Decimal | None = None,
    fraud_flag: float | None = None,
) -> AIDecision:
    record = await get_or_create_decision(db, claim_id)
    record.decision = decision
    record.reason_summary = reason_summary
    record.assessor_memo = memo
    record.customer_explanation = customer_explanation
    record.confidence_score = confidence
    record.suggested_payout = payout
    await db.commit()
    await db.refresh(record)

    claim = await db.get(Claim, claim_id)
    if claim is not None:
        if fraud_flag is not None:
            claim.fraud_risk_score = fraud_flag
            await db.commit()
        await notify_customer(
            db, claim=claim, event=event_for_decision(decision),
            message=customer_explanation, decision_id=record.decision_id,
        )

    return record


def _call_model(prompt: str) -> Decision:
    response = get_gpt_client().responses.parse(
        model=get_gpt_deployment(),
        input=[{"role": "user", "content": prompt}],
        text_format=Decision,
        # Neither temperature nor seed are supported for gpt-5.5 on the
        # Responses API 
    )
    return response.output_parsed

def _build_prompt(
    claim: Claim, assessment: ClaimDamageAssessment, retrieval: dict, consistency: ConsistencyResult, fraud_flag: float
) -> str:
    clauses = "\n".join(
        f"[{m['metadata'].get('section_ref')}] {m['text']}" for m in retrieval["matches"]
    ) or "(none)"
    exclusions = "\n".join(
        f"[{m['metadata'].get('section_ref')}] {m['text']}" for m in retrieval["linked_exclusions"]
    ) or "(none)"
    definitions = "\n".join(f"{d['term']}: {d['meaning']}" for d in retrieval["linked_definitions"]) or "(none)"
    discrepancies = "\n".join(f"  - {d}" for d in consistency.discrepancies) or "  (none)"
    estimated_value = claim.estimated_value if claim.estimated_value is not None else "not provided by claimant"

    return f"""You are deciding whether an insurance claim is covered, based on the
    evidence below. Cite the section_ref of every clause you rely on.

    Also rate, 0-1, your own calibrated view of (a) how consistent the
    claimant's account is with the evidence, and (b) how well the retrieved
    clause(s) actually support your classification.

    Give your own rough, non-binding repair/replacement cost estimate in
    dollars (suggested_payout) based on the damage description and severity,
    informed by the claimant's own estimated_value below if provided - this
    is before any excess or policy limit is applied, those are handled
    separately afterward. Use 0 if excluded or not reasonably estimable from
    the evidence.

    Finally, write a plain-language explanation of the decision suitable to
    send directly to the claimant - clear and respectful, no internal jargon
    or scoring language, though it may reference the relevant policy section.

    Damage assessment (from claim images):
    - description: {assessment.damage_description}
    - damage_type: {assessment.damage_type}
    - severity: {assessment.severity}

    Claimant's own estimated_value of the loss: {estimated_value}

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

    Fraud risk signal (0-1, from claim history, frequency, and image similarity): {fraud_flag}
    """

def _build_memo(
    claim: Claim, assessment: ClaimDamageAssessment, decision: str, reasoning: str,
    retrieval: dict, consistency: ConsistencyResult, composite: float | None, band: str | None,
    retrieval_capped: bool = False, sc_info: dict | None = None, payout_note: str | None = None,
) -> str:
    sections = [
        f"Claim {claim.claim_reference} — Decision: {decision}",
        f"Composite confidence: {composite:.1f} ({band})" if composite is not None else "Composite confidence: n/a (referred before scoring)",
    ]
    if retrieval_capped:
        sections.append(
            "  Note: capped from 'high' - retrieval flagged the matched clause as unreliable "
            "(needs_human_review); the model's own confidence alone doesn't override that."
        )
    if sc_info and sc_info["samples"] > 1:
        sections.append(f"  Self-consistency: {sc_info['samples']} samples, majority {sc_info['agreement']}")
    if payout_note:
        sections.append(f"  {payout_note}")
    sections += [
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





