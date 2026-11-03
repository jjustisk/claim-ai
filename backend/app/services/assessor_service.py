"""Assessor review logic.

Loads the claims queue, claim detail, saves an outcome, and downloads
evidence. Used by the JSON API (what Vue will call). The HTML test UI
in pages/ also uses these helpers until Vue replaces it.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, unquote

from fastapi.responses import Response

from app.api.schemas import ClaimStatus
from app.connectors.db import get_sync_connection
from app.connectors.storage import download_stored_blob
from app.services.claim_form import attach_form_details
from app.services.claim_pii_service import load_pii_mapping_for_claim, rehydrate_assessor_text
from app.services.sanitization_service import sanitize_free_text

AI_STEPS = (
    ("pii_reduction", "Privacy screening"),
    ("damage_description", "AI damage description & analysis"),
    ("consistency_check", "Statement vs photo consistency check"),
    ("fraud_check", "Fraud & duplicate image check"),
    ("policy_match", "Policy clause matching"),
    ("decision", "AI recommendation & confidence"),
)
AI_STEP_LABELS = dict(AI_STEPS)

HIGH_CONFIDENCE_THRESHOLD = 85
MODERATE_CONFIDENCE_THRESHOLD = 70
CONSISTENCY_PASS_THRESHOLD = 0.7
FRAUD_FLAG_THRESHOLD = 0.35

DECISION_PENDING = "pending"
DECISION_REFER = "refer_to_assessor"
_DECISION_LABELS = {
    "covered": "approving the claim (covered)",
    "partial": "approving part of the claim (partial cover)",
    "excluded": "declining the claim (excluded)",
}

STATUS_LABELS = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "approved": "Approved",
    "rejected": "Rejected",
    "closed": "Closed",
}

REVIEW_OUTCOMES = (
    ClaimStatus.UNDER_REVIEW.value,
    ClaimStatus.APPROVED.value,
    ClaimStatus.REJECTED.value,
    ClaimStatus.CLOSED.value,
)


class ReviewError(Exception):
    """Raised when a review cannot be saved."""


def claim_counts() -> dict[str, int]:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) FROM claim WHERE status <> 'draft' GROUP BY status")
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM claim WHERE status <> 'draft'")
            counts["all"] = int(cur.fetchone()[0])
            return counts
    finally:
        conn.close()


def list_claims(status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            c.claim_id,
            c.claim_reference,
            c.status,
            c.submission_date,
            c.priority_level,
            c.fraud_risk_score,
            c.cost,
            c.estimated_value,
            c.incident_description,
            c.claim_type,
            c.insurance_type,
            cu.name AS customer_name,
            cu.email AS customer_email,
            p.policy_number,
            p.coverage_type
        FROM claim c
        JOIN customer cu ON cu.customer_id = c.customer_id
        JOIN policy p ON p.policy_id = c.policy_id
    """
    params: tuple[Any, ...] = ()
    if status == ClaimStatus.DRAFT.value:
        return []
    if status:
        sql += " WHERE c.status = %s"
        params = (status,)
    else:
        sql += " WHERE c.status <> 'draft'"
    sql += " ORDER BY c.submission_date DESC NULLS LAST, c.claim_id DESC"

    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [col[0] for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_claim(claim_id: int) -> dict[str, Any] | None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.*,
                    cu.customer_id,
                    cu.name AS customer_name,
                    cu.email AS customer_email,
                    cu.phone AS customer_phone,
                    p.policy_id,
                    p.policy_number,
                    p.coverage_type
                FROM claim c
                JOIN customer cu ON cu.customer_id = c.customer_id
                JOIN policy p ON p.policy_id = c.policy_id
                WHERE c.claim_id = %s
                """,
                (claim_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            claim = dict(zip([col[0] for col in cur.description], row))
            if claim.get("status") == ClaimStatus.DRAFT.value:
                return None

            cur.execute(
                """
                SELECT doc_id, file_type, file_url, upload_date
                FROM claim_document
                WHERE claim_id = %s
                ORDER BY upload_date, doc_id
                """,
                (claim_id,),
            )
            claim["documents"] = [
                dict(zip([col[0] for col in cur.description], doc))
                for doc in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT decision_id, decision, confidence_score, reason_summary,
                       assessor_memo, customer_explanation, suggested_payout, created_at
                FROM ai_decision
                WHERE claim_id = %s
                ORDER BY created_at DESC, decision_id DESC
                """,
                (claim_id,),
            )
            claim["ai_decisions"] = [
                dict(zip([col[0] for col in cur.description], decision))
                for decision in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT r.assessor_id, a.name, a.email, r.review_date,
                       r.decision_override, r.override_reason, r.outcome
                FROM reviews r
                JOIN assessor a ON a.assessor_id = r.assessor_id
                WHERE r.claim_id = %s
                ORDER BY r.review_date DESC
                """,
                (claim_id,),
            )
            claim["reviews"] = [
                dict(zip([col[0] for col in cur.description], review))
                for review in cur.fetchall()
            ]

            latest_decision = claim["ai_decisions"][0] if claim["ai_decisions"] else None
            claim["audit_trail"] = []
            stages: dict[str, dict[str, Any]] = {}
            if latest_decision:
                cur.execute(
                    """
                    SELECT log_id, action_type, description, timestamp, input_payload, output_payload
                    FROM audit_log
                    WHERE decision_id = %s
                    ORDER BY timestamp, log_id
                    """,
                    (latest_decision["decision_id"],),
                )
                for log_id, action_type, description, timestamp, input_payload, output_payload in cur.fetchall():
                    claim["audit_trail"].append({
                        "log_id": log_id,
                        "action_type": action_type,
                        "description": description,
                        "timestamp": timestamp,
                    })
                    # Rows are oldest first, so each stage ends up with its latest row.
                    stages[action_type] = {
                        "description": description,
                        "input": _payload(input_payload),
                        "output": _payload(output_payload),
                        "timestamp": timestamp,
                    }

            cur.execute(
                """
                SELECT damage_description, reasoning, damage_type, severity, images_assessable,
                       images_available, images_assessed, model, created_at
                FROM claim_damage_assessment
                WHERE claim_id = %s
                ORDER BY created_at DESC, assessment_id DESC
                LIMIT 1
                """,
                (claim_id,),
            )
            damage_row = cur.fetchone()
            damage = dict(zip([col[0] for col in cur.description], damage_row)) if damage_row else None

            image_similarity = (stages.get("generation") or {}).get("input", {}).get("fraud_image_similarity") or {}
            matched_claim = _load_matched_claim(cur, image_similarity)
    finally:
        conn.close()

    claim["similar_image_match"] = _similar_image_match(image_similarity, matched_claim)
    claim["ai_assessment"] = build_ai_assessment(
        claim,
        latest_decision,
        stages,
        damage,
        matched_claim,
        rehydrator(claim_id, claim.get("pii_session_id")),
    )
    return attach_form_details(claim)


def _load_matched_claim(cur: Any, image_similarity: dict[str, Any]) -> dict[str, Any] | None:
    """Return the claim a duplicate image matched, only when the similarity score is above zero."""
    closest = image_similarity.get("closest_match") or {}
    if (_number(image_similarity.get("image_similarity_score")) or 0) <= 0 or not closest.get("matched_claim_id"):
        return None
    cur.execute(
        """
        SELECT c.claim_id, c.claim_reference, cu.name AS customer_name
        FROM claim c
        JOIN customer cu ON cu.customer_id = c.customer_id
        WHERE c.claim_id = %s
        """,
        (closest["matched_claim_id"],),
    )
    row = cur.fetchone()
    return dict(zip([col[0] for col in cur.description], row)) if row else None


def _similar_image_match(
    image_similarity: dict[str, Any], matched_claim: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Return the duplicate-image banner data, or None when no image scored above zero."""
    closest = image_similarity.get("closest_match") or {}
    if not matched_claim or not closest:
        return None
    return {
        "matched_claim_id": closest.get("matched_claim_id"),
        "matched_claim_reference": matched_claim.get("claim_reference"),
        "matched_customer_name": matched_claim.get("customer_name"),
        "matched_doc_id": closest.get("matched_doc_id"),
        "own_doc_id": closest.get("own_doc_id"),
        "hamming_distance": image_similarity.get("hamming_distance"),
        "image_similarity_score": image_similarity.get("image_similarity_score"),
    }


def rehydrator(claim_id: int, session_id: str | None) -> Callable[[Any], Any]:
    """Return a function that swaps PII placeholders back to originals in strings, lists and dicts."""
    mapping = load_pii_mapping_for_claim(claim_id, session_id)

    def rehydrate(value: Any) -> Any:
        if isinstance(value, str):
            return rehydrate_assessor_text(value, claim_id=claim_id, session_id=session_id, mapping=mapping)
        if isinstance(value, list):
            return [rehydrate(item) for item in value]
        if isinstance(value, dict):
            return {key: rehydrate(item) for key, item in value.items()}
        return value

    return rehydrate


def _payload(value: Any) -> dict[str, Any]:
    """Return a JSONB payload as a dict whether it arrives parsed or as text."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    """Return a value as a float, or None when it is missing or not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    """Return a datetime as an ISO string."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _retrieval_action(value: Any) -> str | None:
    """Normalise a stored retrieval action such as 'RetrievalAction.CORRECT' to 'correct'."""
    if value in (None, ""):
        return None
    return str(value).split(".")[-1].strip().lower()


def _plural(count: int, word: str, plural: str | None = None) -> str:
    """Return a count with the singular or plural form of a word."""
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def _short(text: Any, limit: int = 200) -> str:
    """Return text trimmed to one line of at most limit characters."""
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def confidence_band(score: float | None) -> str | None:
    """Return the confidence band for a 0-100 confidence score."""
    if score is None:
        return None
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= MODERATE_CONFIDENCE_THRESHOLD:
        return "moderate"
    return "low"


def _step(key: str, status: str, summary: str, timestamp: Any, details: dict[str, Any]) -> dict[str, Any]:
    """Return one pipeline step in the ai_assessment contract shape."""
    return {
        "key": key,
        "label": AI_STEP_LABELS[key],
        "status": status,
        "summary": summary,
        "timestamp": _iso(timestamp),
        "details": details,
    }


def _not_run(final: bool) -> tuple[str, str]:
    """Return the status and summary for a step that has no data yet."""
    if final:
        return "skipped", "Not run: the pipeline stopped at an earlier step."
    return "pending", "Waiting for this step to run."


def _clauses(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the cited clauses, falling back to the single cited section ref on older rows."""
    cited = output.get("cited_clauses")
    if isinstance(cited, list) and cited:
        return [
            {
                "section_ref": item.get("section_ref"),
                "title": item.get("title"),
                "excerpt": item.get("excerpt"),
                "pds_id": item.get("pds_id"),
                "page": item.get("page"),
                "chunk_type": item.get("chunk_type"),
            }
            for item in cited
            if isinstance(item, dict)
        ]
    ref = output.get("cited_clause_ref")
    if ref:
        return [{"section_ref": ref, "title": None, "excerpt": None, "pds_id": None, "page": None, "chunk_type": None}]
    return []


def _memo(output: dict[str, Any], rehydrate: Callable[[Any], Any]) -> dict[str, Any] | None:
    """Return the structured assessor memo, or None on rows written before it existed."""
    memo = output.get("memo")
    if not isinstance(memo, dict):
        return None
    clauses = memo.get("clauses") if isinstance(memo.get("clauses"), list) else []
    return {
        "summary": rehydrate(memo.get("summary")),
        "explanation": rehydrate(memo.get("explanation")),
        "clauses": [
            {"section_ref": item.get("section_ref"), "how_it_applies": rehydrate(item.get("how_it_applies"))}
            for item in clauses
            if isinstance(item, dict)
        ],
    }


def _pii_step(claim: dict[str, Any], row: dict[str, Any] | None, final: bool) -> dict[str, Any]:
    """Return the privacy screening step from the claim's PII status and audit row."""
    pii_status = claim.get("pii_status")
    description = (row or {}).get("description") or ""
    reason = None
    if pii_status in ("queued", "processing"):
        status, summary = "pending", "Masking personal details before AI analysis."
    elif pii_status == "failed" or (pii_status != "ready" and "fail" in description.lower()):
        reason = _short(description.removeprefix("PII reduction failed:"), 160) or None
        status = "fail"
        summary = f"Privacy screening failed, so no AI model was run: {reason}" if reason else (
            "Privacy screening failed, so no AI model was run."
        )
    elif pii_status == "ready" or row:
        status, summary = "pass", "Personal details were masked before any AI model saw the claim."
    elif final:
        status, summary = "skipped", "No privacy screening record for this claim."
    else:
        status, summary = _not_run(final)
    details = {"pii_status": pii_status, "reason": reason}
    return _step("pii_reduction", status, summary, (row or {}).get("timestamp"), details)


def _same_run(damage: dict[str, Any], decision: dict[str, Any] | None) -> bool:
    """Return True when the Call 1 result was written during the given AI decision's run."""
    created, assessed = (decision or {}).get("created_at"), damage.get("created_at")
    try:
        return created is not None and assessed is not None and assessed >= created
    except TypeError:
        return False


def _damage_step(
    row: dict[str, Any] | None,
    damage: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    final: bool,
    rehydrate: Callable[[Any], Any],
) -> dict[str, Any]:
    """Return the damage description step from Call 1's assessment row and audit payload."""
    output = (row or {}).get("output") or {}
    inputs = (row or {}).get("input") or {}
    if row and not output:
        return _step(
            "damage_description",
            "fail",
            "The AI could not assess the claim photos.",
            row.get("timestamp"),
            {"reasoning": rehydrate(row.get("description"))},
        )
    data: dict[str, Any] = dict(damage) if damage and (output or _same_run(damage, decision)) else {}
    data.update({key: value for key, value in output.items() if value is not None})
    for key in ("images_available", "images_assessed"):
        if inputs.get(key) is not None:
            data[key] = inputs[key]
    if not data:
        status, summary = _not_run(final)
        return _step("damage_description", status, summary, None, {})

    severity = str(data.get("severity") or "").replace("_", " ")
    damage_type = str(data.get("damage_type") or "").replace("_", " ")
    damage_type = "" if damage_type == "other" else damage_type
    obj = data.get("object_identified")
    assessed, available = data.get("images_assessed"), data.get("images_available")
    if data.get("images_assessable") is False:
        status, summary = "flag", "The photos were not clear enough for the AI to assess the damage."
    else:
        status = "pass"
        if severity == "none":
            finding = "No visible damage"
        else:
            finding = " ".join(part for part in (severity, damage_type) if part) + " damage"
        summary = f"{obj}: {finding.lower()}" if obj else finding[:1].upper() + finding[1:]
        if assessed is not None and available is not None:
            summary += f" ({assessed} of {_plural(int(available), 'photo')} assessed)"
        summary += "."
    affected = data.get("affected_areas")
    return _step(
        "damage_description",
        status,
        rehydrate(summary),
        (row or {}).get("timestamp") or data.get("created_at"),
        {
            "description": rehydrate(data.get("damage_description")),
            "damage_type": data.get("damage_type"),
            "severity": data.get("severity"),
            "object_identified": rehydrate(obj),
            "damage_age_estimate": data.get("damage_age_estimate"),
            "affected_areas": rehydrate(affected) if isinstance(affected, list) else [],
            "images_assessable": data.get("images_assessable"),
            "images_assessed": assessed,
            "images_available": available,
            "reasoning": rehydrate(data.get("reasoning")),
        },
    )


def _consistency_step(
    row: dict[str, Any] | None,
    generation_input: dict[str, Any],
    final: bool,
    rehydrate: Callable[[Any], Any],
) -> dict[str, Any]:
    """Return the statement vs photo consistency step from Call 2's audit payload."""
    output = (row or {}).get("output") or {}
    flag = _number(output.get("consistency_flag"))
    if flag is None:
        flag = _number(generation_input.get("consistency_flag"))
    if flag is None:
        status, summary = _not_run(final)
        return _step("consistency_check", status, summary, (row or {}).get("timestamp"), {})

    discrepancies = output.get("discrepancies") if isinstance(output.get("discrepancies"), list) else []
    count = len(discrepancies)
    if flag >= CONSISTENCY_PASS_THRESHOLD:
        status = "pass"
        summary = f"The claimant's account matches the photos (score {flag:.2f})."
        if count:
            summary = (
                f"The claimant's account broadly matches the photos, with "
                f"{_plural(count, 'minor difference')} (score {flag:.2f})."
            )
    else:
        status = "flag"
        if count:
            summary = (
                f"{_plural(count, 'discrepancy', 'discrepancies')} between the claimant's account "
                f"and the photos (score {flag:.2f})."
            )
        else:
            summary = f"The claimant's account only partly matches the photos (score {flag:.2f})."
    return _step(
        "consistency_check",
        status,
        summary,
        (row or {}).get("timestamp"),
        {
            "consistency_flag": flag,
            "discrepancies": rehydrate(discrepancies),
            "reasoning": rehydrate(output.get("reasoning")),
        },
    )


def _fraud_step(
    generation: dict[str, Any] | None,
    matched_claim: dict[str, Any] | None,
    final: bool,
) -> dict[str, Any]:
    """Return the fraud and duplicate image step from the generation input payload."""
    inputs = (generation or {}).get("input") or {}
    fraud_flag = _number(inputs.get("fraud_flag"))
    if fraud_flag is None:
        status, summary = _not_run(final)
        return _step("fraud_check", status, summary, (generation or {}).get("timestamp"), {})

    history = inputs.get("fraud_history") or {}
    frequency = inputs.get("fraud_frequency") or {}
    similarity = inputs.get("fraud_image_similarity") or {}
    closest = similarity.get("closest_match") or {}
    score = _number(similarity.get("image_similarity_score")) or 0.0
    image_match = None
    if score > 0 and closest:
        image_match = {
            "matched_claim_id": closest.get("matched_claim_id"),
            "matched_claim_reference": (matched_claim or {}).get("claim_reference"),
            "matched_doc_id": closest.get("matched_doc_id"),
            "own_doc_id": closest.get("own_doc_id"),
            "hamming_distance": similarity.get("hamming_distance"),
            "score": score,
        }

    reasons = []
    if image_match:
        other = image_match["matched_claim_reference"] or f"#{image_match['matched_claim_id']}"
        reasons.append(f"a submitted photo closely matches an image on claim {other}")
    if fraud_flag >= FRAUD_FLAG_THRESHOLD:
        reasons.append(f"the fraud risk score of {fraud_flag:.2f} is at or above the {FRAUD_FLAG_THRESHOLD} threshold")
    if reasons:
        status = "flag"
        summary = "; ".join(reasons)
        summary = summary[:1].upper() + summary[1:] + "."
    else:
        status = "pass"
        summary = f"No duplicate photos found and the fraud risk score is low ({fraud_flag:.2f})."
    return _step(
        "fraud_check",
        status,
        summary,
        generation.get("timestamp"),
        {
            "fraud_flag": fraud_flag,
            "claim_count": history.get("claim_count"),
            "rejection_rate": _number(history.get("rejection_rate")),
            "days_since_last_claim": frequency.get("days_since_last_claim"),
            "image_match": image_match,
        },
    )


def _policy_step(
    generation: dict[str, Any] | None,
    clauses: list[dict[str, Any]],
    final: bool,
    rehydrate: Callable[[Any], Any],
) -> dict[str, Any]:
    """Return the policy clause matching step from the generation payloads."""
    inputs = (generation or {}).get("input") or {}
    output = (generation or {}).get("output") or {}
    action = _retrieval_action(inputs.get("retrieval_action"))
    if action is None:
        status, summary = _not_run(final)
        return _step("policy_match", status, summary, (generation or {}).get("timestamp"), {})

    needs_review = bool(inputs.get("retrieval_needs_human_review"))
    refs = ", ".join(str(c["section_ref"]) for c in clauses[:3] if c.get("section_ref"))
    if action == "correct" and not needs_review and clauses:
        status = "pass"
        summary = f"Matched policy {'clause' if len(clauses) == 1 else 'clauses'} {refs}." if refs else (
            "Matched a policy clause."
        )
    elif action == "incorrect" or not clauses:
        status = "flag"
        summary = "No policy clause clearly matched this claim; check the PDS."
    else:
        status = "flag"
        summary = (
            f"More than one clause could apply ({refs}); assessor should confirm."
            if refs
            else "The clause match is uncertain; assessor should confirm."
        )
    return _step(
        "policy_match",
        status,
        summary,
        generation.get("timestamp"),
        {
            "action": action,
            "needs_human_review": needs_review,
            "reasoning": rehydrate(output.get("retrieval_reasoning")),
            "clauses": clauses,
        },
    )


def _decision_step(
    decision: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    score: float | None,
    band: str | None,
    rehydrate: Callable[[Any], Any],
) -> dict[str, Any]:
    """Return the AI recommendation step from the decision row and generation output."""
    value = (decision or {}).get("decision")
    if value in (None, DECISION_PENDING):
        status, summary = _not_run(False)
        return _step("decision", status, summary, None, {})

    output = (generation or {}).get("output") or {}
    payout = _number(output.get("payout"))
    if payout is None and "payout" not in output:
        payout = _number(decision.get("suggested_payout"))
    if value == DECISION_REFER:
        status = "flag"
        if score is None:
            reason = _short(rehydrate(decision.get("reason_summary") or (generation or {}).get("description")))
            summary = f"Referred to an assessor before scoring: {reason}" if reason else (
                "Referred to an assessor before scoring."
            )
        elif band == "low":
            summary = (
                f"Referred to an assessor: {score:.0f}% confidence is below the "
                f"{MODERATE_CONFIDENCE_THRESHOLD}% threshold."
            )
        else:
            summary = f"Referred to an assessor at {score:.0f}% confidence."
    else:
        status = "pass" if band == "high" else "flag"
        label = _DECISION_LABELS.get(value, value)
        summary = (
            f"Recommends {label} with {score:.0f}% confidence ({band})."
            if score is not None
            else f"Recommends {label}."
        )
    return _step(
        "decision",
        status,
        summary,
        (generation or {}).get("timestamp") or decision.get("created_at"),
        {
            "decision": value,
            "coverage_decision": output.get("coverage_decision"),
            "confidence_score": score,
            "band": band,
            "payout": payout,
            "retrieval_capped": output.get("retrieval_capped"),
            "self_consistency_samples": output.get("self_consistency_samples"),
            "self_consistency_agreement": output.get("self_consistency_agreement"),
            "reasoning": rehydrate(output.get("reasoning")),
        },
    )


def build_ai_assessment(
    claim: dict[str, Any],
    decision: dict[str, Any] | None,
    stages: dict[str, dict[str, Any]],
    damage: dict[str, Any] | None,
    matched_claim: dict[str, Any] | None,
    rehydrate: Callable[[Any], Any],
) -> dict[str, Any]:
    """Return the assessor-facing AI assessment built from the decision, audit rows and Call 1 result."""
    value = (decision or {}).get("decision")
    final = value not in (None, DECISION_PENDING)
    generation = stages.get("generation")
    output = (generation or {}).get("output") or {}
    inputs = (generation or {}).get("input") or {}

    score = _number((decision or {}).get("confidence_score"))
    if score is None:
        score = _number(output.get("confidence_score"))
    score = round(score, 1) if score is not None else None
    band = output.get("band") if output.get("band") in ("high", "moderate", "low") else confidence_band(score)
    if "band" not in output and band == "high" and output.get("retrieval_capped"):
        band = "moderate"
    clauses = _clauses(output)
    explanation = rehydrate((decision or {}).get("customer_explanation"))

    if not final:
        status = "pending"
    elif value == DECISION_REFER:
        status = "referred"
    else:
        status = "complete"

    return {
        "status": status,
        "decision": value,
        "recommended_payout": _number((decision or {}).get("suggested_payout")),
        "confidence": {
            "score": score,
            "band": band,
            "signals": {
                "consistency": _number(output.get("adjusted_consistency")),
                "policy_match": _number(output.get("adjusted_rag")),
                "fraud_risk": _number(inputs.get("fraud_flag")),
            },
        },
        "memo": _memo(output, rehydrate),
        "memo_text": rehydrate((decision or {}).get("assessor_memo")),
        "customer_explanation": html.unescape(explanation) if explanation else explanation,
        "clauses": clauses,
        "steps": [
            _pii_step(claim, stages.get("pii_reduction"), final),
            _damage_step(stages.get("damage_description"), damage, decision, final, rehydrate),
            _consistency_step(stages.get("consistency_check"), inputs, final, rehydrate),
            _fraud_step(generation, matched_claim, final),
            _policy_step(generation, clauses, final, rehydrate),
            _decision_step(decision, generation, score, band, rehydrate),
        ],
    }


def customer_explanation_edited(claim: dict[str, Any] | None, submitted: str | None) -> bool:
    """Return True when the assessor changed the customer explanation they were shown."""
    if submitted is None:
        return False
    shown = ((claim or {}).get("ai_assessment") or {}).get("customer_explanation") or ""
    return sanitize_free_text(submitted) != sanitize_free_text(shown)


def save_review(
    assessor_id: int,
    claim_id: int,
    outcome: str,
    notes: str,
    customer_explanation: str | None = None,
    suggested_payout: float | None = None,
) -> None:
    if outcome not in REVIEW_OUTCOMES:
        raise ReviewError("Choose a valid outcome.")
    if outcome == ClaimStatus.REJECTED.value and not notes.strip():
        raise ReviewError("Add notes when rejecting a claim.")

    notes = sanitize_free_text(notes)
    override = bool(notes) or outcome in {
        ClaimStatus.APPROVED.value,
        ClaimStatus.REJECTED.value,
        ClaimStatus.CLOSED.value,
    }
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM claim WHERE claim_id = %s",
                (claim_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ReviewError("Claim not found.")
            if row[0] == ClaimStatus.DRAFT.value:
                raise ReviewError("Draft claims cannot be reviewed.")

            cur.execute(
                """
                INSERT INTO reviews (
                    assessor_id, claim_id, review_date,
                    decision_override, override_reason, outcome
                )
                VALUES (%s, %s, NOW(), %s, %s, %s)
                ON CONFLICT (assessor_id, claim_id) DO UPDATE SET
                    review_date = EXCLUDED.review_date,
                    decision_override = EXCLUDED.decision_override,
                    override_reason = EXCLUDED.override_reason,
                    outcome = EXCLUDED.outcome
                """,
                (assessor_id, claim_id, override, notes or None, outcome),
            )
            cur.execute(
                """
                UPDATE claim
                SET status = %s,
                    outcome_date = CASE
                        WHEN %s IN ('approved', 'rejected', 'closed') THEN NOW()
                        ELSE outcome_date
                    END
                WHERE claim_id = %s
                """,
                (outcome, outcome, claim_id),
            )
            if customer_explanation is not None:
                explanation = sanitize_free_text(customer_explanation)
                cur.execute(
                    """
                    UPDATE ai_decision
                    SET customer_explanation = %s
                    WHERE decision_id = (
                        SELECT decision_id FROM ai_decision
                        WHERE claim_id = %s
                        ORDER BY created_at DESC, decision_id DESC
                        LIMIT 1
                    )
                    """,
                    (explanation or None, claim_id),
                )
            if suggested_payout is not None:
                cur.execute(
                    "UPDATE claim SET cost = %s WHERE claim_id = %s",
                    (suggested_payout, claim_id),
                )
                cur.execute(
                    """
                    UPDATE ai_decision
                    SET suggested_payout = %s
                    WHERE decision_id = (
                        SELECT decision_id FROM ai_decision
                        WHERE claim_id = %s
                        ORDER BY created_at DESC, decision_id DESC
                        LIMIT 1
                    )
                    """,
                    (suggested_payout, claim_id),
                )
        conn.commit()
    finally:
        conn.close()


def get_document(doc_id: int) -> dict[str, Any] | None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, claim_id, file_type, file_url
                FROM claim_document
                WHERE doc_id = %s
                """,
                (doc_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return dict(zip([col[0] for col in cur.description], row))
    finally:
        conn.close()


def evidence_filename(file_url: str, doc_id: int) -> str:
    name = unquote(str(file_url or "").replace("\\", "/").split("/")[-1])
    match = re.match(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-(.+)",
        name,
        re.I,
    )
    return match.group(1) if match else (name or f"document-{doc_id}")


def evidence_download_response(
    data: bytes,
    filename: str,
    media_type: str | None,
    *,
    disposition: str = "attachment",
) -> Response:
    safe = filename.replace("\\", "_").replace('"', "").replace("\r", "").replace("\n", "")
    ascii_name = safe.encode("ascii", "replace").decode("ascii") or "document"
    return Response(
        content=data,
        media_type=media_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


async def download_claim_document(doc_id: int) -> tuple[bytes, str, str] | None:
    doc = get_document(doc_id)
    if doc is None or not doc.get("file_url"):
        return None
    stored = str(doc["file_url"])
    data = await download_stored_blob(stored)
    filename = evidence_filename(stored, doc_id)
    media_type = str(doc["file_type"] or "application/octet-stream")
    return data, filename, media_type


def get_claim_policy_document(claim_id: int) -> dict[str, Any] | None:
    """Return the PDS row for the product on a submitted claim's policy."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.pds_id, d.product_id, d.version, d.file_url, d.effective_date
                FROM claim c
                JOIN policy p ON p.policy_id = c.policy_id
                JOIN pds_document d ON d.product_id = p.product_id AND d.version = 'PDS'
                WHERE c.claim_id = %s AND c.status <> 'draft'
                ORDER BY d.effective_date DESC NULLS LAST, d.pds_id DESC
                LIMIT 1
                """,
                (claim_id,),
            )
            row = cur.fetchone()
            return dict(zip([col[0] for col in cur.description], row)) if row else None
    finally:
        conn.close()


async def download_claim_policy_document(claim_id: int) -> tuple[bytes, str] | None:
    """Download a claim's product PDS and return its bytes and a PDF filename."""
    doc = get_claim_policy_document(claim_id)
    if doc is None or not doc.get("file_url"):
        return None
    stored = str(doc["file_url"])
    data = await download_stored_blob(stored)
    filename = unquote(stored.rstrip("/").split("/")[-1].split("?")[0])
    if not filename.lower().endswith(".pdf"):
        filename = f"pds-{doc['pds_id']}.pdf"
    return data, filename
