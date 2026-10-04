"""Human-readable decision brief for assessors (separate from raw AI pipeline artefacts).

Produces a scannable Claim-AI preliminary decision document. Does not modify
ai_decision rows or generation output. Assessor-facing text is rehydrated so
placeholders like ADDRESS_2 are replaced with original values.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.connectors.db import get_sync_connection
from app.connectors.foundry import get_gpt_client, get_mini_deployment
from app.services.claim_pii_service import load_pii_mapping_for_claim, rehydrate_assessor_text

_STATUS_BANNER: dict[str, str] = {
    "covered": "🟢 **ACCEPT RECOMMENDED**",
    "partial": "🟡 **PARTIAL ACCEPTANCE RECOMMENDED**",
    "excluded": "🔴 **DECLINE RECOMMENDED**",
    "refer_to_assessor": "🟠 **MANUAL REVIEW REQUIRED**",
}

_OUTCOME_TITLE: dict[str, str] = {
    "covered": "Accept — claim appears covered",
    "partial": "Partial acceptance — some loss appears covered",
    "excluded": "Decline — exclusion or policy condition appears to apply",
    "refer_to_assessor": "Refer for manual assessment",
}

_NO_PAYOUT_DECISIONS = frozenset({"refer_to_assessor", "excluded"})
# Fraud flag is 0–1 from history + frequency + image similarity.
_FRAUD_ALERT_THRESHOLD = 0.35
_FRAUD_HIGH_THRESHOLD = 0.60

_BRIEF_SYSTEM = """You rewrite Claim-AI preliminary decision briefs for human assessors.

Return Markdown only, using EXACTLY this section structure:

# CLAIM-AI — PRELIMINARY DECISION BRIEF
(optional fraud alert block if fraud_alert is true)
header metadata
## 1. Claim Summary
## 2. Assessment Summary
## 3. What the Customer Reported
## 4. What the Images Show
## 5. Key Evidence Discrepancy
## 6. Policy Review
## 7. Automated Assessment
## 8. Payment Recommendation
## 9. Assessor Action Required
### Claim-AI Note

Rules:
- Plain professional English. Scannable.
- Under What the Customer Reported: include the exact customer text first, then highlights.
- If fraud_alert is true, keep the red fraud warning at the top with reasons.
- Do NOT invent dollars. On refer/excluded: no payment recommendation.
- Do NOT mention ML/RAG/Call 1/Call 2."""


def _clean_text(value: Any, *, limit: int = 2000) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _money(value: Any) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except Exception:
        return None
    if amount <= 0:
        return None
    return f"${amount:,.0f}"


def _decision_key(facts: dict[str, Any]) -> str:
    return str((facts.get("ai_decision") or {}).get("decision") or "refer_to_assessor")


def _payment_allowed(facts: dict[str, Any]) -> bool:
    return _decision_key(facts) not in _NO_PAYOUT_DECISIONS


def _indicative_payment(facts: dict[str, Any]) -> str | None:
    if not _payment_allowed(facts):
        return None
    return _money((facts.get("ai_decision") or {}).get("suggested_payout"))


def _customer_exact_text(facts: dict[str, Any]) -> str:
    """Exact words the customer typed (original claim fields — for assessors)."""
    parts = []
    incident = _clean_text(facts.get("incident_description"), limit=2000)
    loss = _clean_text(facts.get("loss_description"), limit=1200)
    comments = _clean_text(facts.get("additional_comments"), limit=800)
    if incident:
        parts.append(incident)
    if loss:
        parts.append(loss)
    if comments:
        parts.append(comments)
    return "\n\n".join(parts)


def _bulletise_incident(text: str) -> list[str]:
    if not text:
        return ["No incident description was recorded on the claim."]
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    bullets = [p.strip() for p in parts if p.strip()]
    if len(bullets) == 1 and len(bullets[0]) > 180:
        return [bullets[0]]
    return bullets[:8] or [text]


def _fraud_score(facts: dict[str, Any]) -> float:
    raw = facts.get("fraud_risk_score")
    if raw is None:
        gen_in = facts.get("generation_input") or {}
        raw = gen_in.get("fraud_flag")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _fraud_reasons(facts: dict[str, Any]) -> list[str]:
    """Plain-language reasons the fraud signal is elevated."""
    reasons: list[str] = []
    gen_in = facts.get("generation_input") or {}
    history = gen_in.get("fraud_history") or {}
    frequency = gen_in.get("fraud_frequency") or {}
    image_sim = gen_in.get("fraud_image_similarity") or {}

    count = history.get("claim_count")
    if count is not None and int(count) >= 2:
        reasons.append(
            f"This customer has submitted **{int(count)} other claim(s)** in the last 12 months."
        )
    rate = history.get("rejection_rate")
    if rate is not None and float(rate) > 0.10:
        pct = round(float(rate) * 100)
        reasons.append(f"Prior claims for this customer show a **{pct}% rejection rate**.")

    days = frequency.get("days_since_last_claim")
    if days is not None and int(days) < 90:
        reasons.append(
            f"Another claim was lodged only **{int(days)} day(s)** before this one."
        )

    sim_score = image_sim.get("image_similarity_score")
    matched = image_sim.get("matched_claim_reference") or image_sim.get("matched_claim_id")
    if sim_score is not None and float(sim_score) >= 0.3:
        if matched:
            reasons.append(
                f"Submitted photos are **similar to images on another claim** ({matched})."
            )
        else:
            reasons.append(
                "Submitted photos are **similar to images already on file for another claim**."
            )

    if facts.get("similar_image_match"):
        sim = facts["similar_image_match"]
        reasons.append(
            "Similar photo match flagged against claim "
            f"**{sim.get('matched_claim_reference') or sim.get('matched_claim_id')}** "
            f"({sim.get('matched_customer_name') or 'another customer'})."
        )

    discrepancies = (facts.get("consistency") or {}).get("discrepancies") or []
    if discrepancies and _fraud_score(facts) >= _FRAUD_ALERT_THRESHOLD:
        reasons.append(
            "The customer's written account **does not match** the damage visible in the photos, "
            "which increases the need for careful fraud / evidence review."
        )

    if not reasons and _fraud_score(facts) >= _FRAUD_ALERT_THRESHOLD:
        reasons.append(
            "The combined fraud risk signal from claim history, lodging frequency, "
            "and/or image similarity is elevated."
        )
    return reasons


def _load_facts(claim_id: int) -> dict[str, Any] | None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.claim_id, c.claim_reference, c.incident_date, c.incident_description,
                       c.loss_description, c.additional_comments, c.estimated_value,
                       c.pii_status, c.pii_session_id, c.llm_payload_json, c.fraud_risk_score,
                       c.insurance_type, c.claim_type, c.submission_date,
                       p.policy_number, p.coverage_type,
                       cu.name AS customer_name
                FROM claim c
                JOIN policy p ON p.policy_id = c.policy_id
                JOIN customer cu ON cu.customer_id = c.customer_id
                WHERE c.claim_id = %s
                """,
                (claim_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            facts: dict[str, Any] = dict(zip(cols, row))
            facts.pop("llm_payload_json", None)

            cur.execute(
                """
                SELECT vehicle_registration, vehicle_make, vehicle_model, vehicle_year,
                       vehicle_type, vehicle_damage_areas
                FROM motor_claim WHERE claim_id = %s
                """,
                (claim_id,),
            )
            motor = cur.fetchone()
            if motor:
                facts["motor"] = dict(zip([d[0] for d in cur.description], motor))

            cur.execute("SELECT COUNT(*) FROM claim_document WHERE claim_id = %s", (claim_id,))
            facts["document_count"] = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*) FROM claim_document
                WHERE claim_id = %s AND file_type IN ('image/jpeg', 'image/png')
                """,
                (claim_id,),
            )
            facts["image_count"] = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT damage_description, damage_type, severity, images_assessable,
                       images_assessed, reasoning
                FROM claim_damage_assessment
                WHERE claim_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (claim_id,),
            )
            dmg = cur.fetchone()
            if dmg:
                facts["damage"] = dict(zip([d[0] for d in cur.description], dmg))

            cur.execute(
                """
                SELECT decision_id, decision, confidence_score, reason_summary,
                       customer_explanation, suggested_payout, created_at
                FROM ai_decision
                WHERE claim_id = %s
                ORDER BY created_at DESC, decision_id DESC
                LIMIT 1
                """,
                (claim_id,),
            )
            dec = cur.fetchone()
            if not dec:
                return facts

            facts["ai_decision"] = dict(zip([d[0] for d in cur.description], dec))
            decision_id = facts["ai_decision"]["decision_id"]

            cur.execute(
                """
                SELECT input_payload, output_payload FROM audit_log
                WHERE decision_id = %s AND action_type = 'generation'
                ORDER BY timestamp DESC LIMIT 1
                """,
                (decision_id,),
            )
            gen = cur.fetchone()
            if gen:
                if gen[0]:
                    facts["generation_input"] = (
                        gen[0] if isinstance(gen[0], dict) else json.loads(gen[0])
                    )
                if gen[1]:
                    facts["generation"] = (
                        gen[1] if isinstance(gen[1], dict) else json.loads(gen[1])
                    )

            cur.execute(
                """
                SELECT output_payload FROM audit_log
                WHERE decision_id = %s AND action_type = 'consistency_check'
                ORDER BY timestamp DESC LIMIT 1
                """,
                (decision_id,),
            )
            con = cur.fetchone()
            if con and con[0]:
                facts["consistency"] = con[0] if isinstance(con[0], dict) else json.loads(con[0])

            return facts
    finally:
        conn.close()


def _summary_lead(decision_key: str, discrepancies: list[Any], damage: dict[str, Any]) -> str:
    if decision_key == "refer_to_assessor" and discrepancies:
        return (
            "The automated review identified a **material discrepancy between the damage "
            "described by the customer and the damage visible in the submitted photographs**."
        )
    if decision_key == "refer_to_assessor" and damage and not damage.get("images_assessable"):
        return (
            "The automated review could not complete a reliable visual assessment from the "
            "submitted photographs."
        )
    if decision_key == "refer_to_assessor":
        return (
            "The automated review **did not reach a confident outcome** and requires "
            "manual assessment before any payment decision."
        )
    if decision_key == "excluded":
        return (
            "The automated review indicates an **exclusion or policy condition** appears "
            "to apply to the claimed loss."
        )
    if decision_key == "partial":
        return (
            "The automated review indicates **part of the claimed loss** may be covered, "
            "subject to limits and excess."
        )
    return (
        "The automated review indicates the claimed loss **appears covered** under the "
        "policy terms reviewed."
    )


def _format_date(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d %B %Y")
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def _template_brief(facts: dict[str, Any]) -> str:
    ref = facts.get("claim_reference") or "Unknown"
    policy = facts.get("policy_number") or "—"
    cover = facts.get("coverage_type") or "Policy cover on file"
    prepared = datetime.now(timezone.utc).strftime("%d %B %Y")
    decision_key = _decision_key(facts)
    status = _STATUS_BANNER.get(decision_key, _STATUS_BANNER["refer_to_assessor"])
    outcome = _OUTCOME_TITLE.get(decision_key, _OUTCOME_TITLE["refer_to_assessor"])
    damage = facts.get("damage") or {}
    consistency = facts.get("consistency") or {}
    discrepancies = list(consistency.get("discrepancies") or [])
    gen = facts.get("generation") or {}
    ai = facts.get("ai_decision") or {}
    clause = _clean_text(gen.get("cited_clause_ref") or "", limit=120)
    reasoning = _clean_text(gen.get("reasoning") or ai.get("reason_summary") or "", limit=700)
    if "pii reduction" in reasoning.lower() or "cascadeclassifier" in reasoning.lower():
        reasoning = ""
    payout = _indicative_payment(facts)
    customer_estimate = _money(facts.get("estimated_value"))
    exact = _customer_exact_text(facts)
    bullets = _bulletise_incident(exact)
    motor = facts.get("motor") or {}
    fraud_score = _fraud_score(facts)
    fraud_reasons = _fraud_reasons(facts) if fraud_score >= _FRAUD_ALERT_THRESHOLD else []

    lines: list[str] = [
        "# CLAIM-AI — PRELIMINARY DECISION BRIEF",
        "",
    ]

    if fraud_reasons:
        level = "HIGH" if fraud_score >= _FRAUD_HIGH_THRESHOLD else "ELEVATED"
        lines += [
            '<div class="fraud-alert">',
            "",
            f"### 🚨 POSSIBLE FRAUD — {level} RISK",
            "",
            f"**Fraud risk score:** {fraud_score:.0%} (automated signal).",
            "",
            "**Why this looks suspicious:**",
            "",
        ]
        for reason in fraud_reasons:
            lines.append(f"* {reason}")
        lines += [
            "",
            "**Assessor action:** Treat this claim with heightened scrutiny before approving payment.",
            "",
            "</div>",
            "",
        ]

    lines += [
        f"**Claim:** {ref}",
        f"**Customer:** {facts.get('customer_name') or '—'}",
        f"**Policy:** {policy}",
        f"**Policy Type:** {cover}",
        f"**Assessment Date:** {prepared}",
        f"**Status:** {status}",
        "",
        "---",
        "",
        "## 1. Claim Summary",
        "",
        "| Field | Detail |",
        "| --- | --- |",
        f"| Claim reference | {ref} |",
        f"| Customer | {facts.get('customer_name') or '—'} |",
        f"| Policy | {policy} ({cover}) |",
        f"| Incident date | {_format_date(facts.get('incident_date'))} |",
        f"| Submitted | {_format_date(facts.get('submission_date'))} |",
        f"| Photos on file | {facts.get('image_count', 0)} |",
        f"| Other files | {facts.get('document_count', 0)} |",
        f"| Customer repair estimate | {customer_estimate or 'Not provided'} |",
    ]
    if motor:
        vehicle_bits = " ".join(
            str(x)
            for x in (
                motor.get("vehicle_year"),
                motor.get("vehicle_make"),
                motor.get("vehicle_model"),
            )
            if x
        ) or "—"
        lines.append(f"| Vehicle | {vehicle_bits} |")
        if motor.get("vehicle_registration"):
            lines.append(f"| Registration | {motor.get('vehicle_registration')} |")
        if motor.get("vehicle_damage_areas"):
            lines.append(
                f"| Reported damage areas | {str(motor.get('vehicle_damage_areas')).replace(',', ', ')} |"
            )

    lines += [
        "",
        "---",
        "",
        "## 2. Assessment Summary",
        "",
        "### Preliminary Outcome",
        "",
        f"**{outcome}**",
        "",
        _summary_lead(decision_key, discrepancies, damage),
        "",
    ]

    if payout:
        lines.append(f"**Indicative payment (before excess):** {payout}")
    else:
        lines.append("**No payment recommendation has been made.**")

    lines += [
        "",
        (
            "> **Assessor decision required:** Confirm the damage, establish whether the "
            "claimed loss is supported by the available evidence, and determine whether "
            "the policy provides coverage."
            if decision_key == "refer_to_assessor"
            else (
                "> **Assessor decision required:** Confirm the policy position, apply any "
                "excess or conditions, then approve, amend, or decline."
            )
        ),
        "",
        "---",
        "",
        "## 3. What the Customer Reported",
        "",
        "### Exact customer statement",
        "",
    ]
    if exact:
        lines += [
            "> " + exact.replace("\n", "\n> "),
            "",
        ]
    else:
        lines += ["> No incident description was recorded on the claim.", ""]

    lines += [
        "### Highlights",
        "",
        "Key points from the customer's account:",
        "",
    ]
    for bullet in bullets:
        lines.append(f"* {bullet}")

    lines += ["", "---", "", "## 4. What the Images Show", ""]
    image_count = int(facts.get("image_count") or 0)
    if not damage:
        lines.append(
            f"{image_count} photo(s) are on file, but no automated visual assessment "
            "result is available yet."
        )
    elif not damage.get("images_assessable"):
        lines += [
            "The submitted photographs were **not sufficient** for a reliable visual assessment.",
            "",
            "Please review the images manually.",
        ]
    else:
        desc = _clean_text(damage.get("damage_description"), limit=700)
        lines += [
            desc or "Damage was visible in the submitted photographs.",
            "",
            "### Automated assessment",
            "",
            "| Attribute | Assessment |",
            "| --- | --- |",
            f"| Photos assessed | {damage.get('images_assessed') or image_count} |",
            f"| Damage type | {str(damage.get('damage_type') or '—').replace('_', ' ')} |",
            f"| Severity | **{str(damage.get('severity') or '—').title()}** |",
            f"| Images assessable | {'Yes' if damage.get('images_assessable') else 'No'} |",
        ]

    lines += [
        "",
        "---",
        "",
        "## 5. Key Evidence Discrepancy",
        "",
    ]
    if discrepancies:
        lines += [
            "### ⚠️ Customer account does not currently align with photographic evidence",
            "",
            "| Issue noted by automated review |",
            "| --- |",
        ]
        for item in discrepancies[:6]:
            lines.append(f"| {_clean_text(item, limit=220)} |")
        lines += [
            "",
            "**Assessment:** The available photographs do not currently corroborate the "
            "damage described in the customer's account.",
            "",
            "This discrepancy prevents the automated review from confidently determining "
            "the claimed loss or recommending a payment amount.",
        ]
    else:
        lines.append(
            "No material inconsistencies were flagged between the customer's description "
            "and the photo review."
        )

    lines += [
        "",
        "---",
        "",
        "## 6. Policy Review",
        "",
        f"**Policy:** {cover}  ",
        f"**Policy reference:** {policy}",
        "",
    ]
    if clause:
        lines += [
            f"Policy section considered during automated review: **{clause}**.",
            "",
        ]
        if reasoning:
            lines.append(reasoning)
    else:
        lines += [
            "No relevant policy clause was retrieved during the automated review.",
            "",
            "Therefore:",
            "",
            "* No coverage clause has been identified to support the claimed incident.",
            "* No exclusion has been identified.",
            "* No policy definition has been retrieved for this assessment.",
            "* **No policy section reference can be provided.**",
            "",
            (
                "> **Important:** The absence of a retrieved policy clause should not be "
                "treated as a coverage determination. The policy wording should be "
                "reviewed manually."
            ),
        ]
        if reasoning:
            lines += ["", reasoning]

    lines += ["", "---", "", "## 7. Automated Assessment", ""]
    if decision_key == "refer_to_assessor":
        lines.append("### Confidence: Insufficient for automated decision")
        lines.append("")
        lines.append("The automated review **did not reach a confident outcome** because:")
        lines.append("")
        reasons: list[str] = []
        if discrepancies:
            reasons.append(
                "**Evidence mismatch** — the customer's account and the photographs "
                "do not currently align."
            )
        if damage and not damage.get("images_assessable"):
            reasons.append(
                "**Insufficient photos** — the images were not clear enough for a "
                "reliable visual assessment."
            )
        if not clause:
            reasons.append(
                "**Policy evidence unavailable** — no relevant policy clause was "
                "retrieved for automated coverage assessment."
            )
        if fraud_reasons:
            reasons.append(
                "**Elevated fraud signal** — see the fraud alert at the top of this brief."
            )
        if not reasons:
            reasons.append(
                "**Low confidence** — the automated review could not safely finalise "
                "coverage or payment."
            )
        for idx, reason in enumerate(reasons, start=1):
            title, _, detail = reason.partition(" — ")
            lines.append(f"**{idx}. {title.replace('**', '')}**")
            if detail:
                lines.append(detail)
            lines.append("")
    else:
        conf = ai.get("confidence_score")
        conf_txt = f"{float(conf):.0f}%" if conf is not None else "not stated"
        lines.append(f"### Confidence: {conf_txt} (preliminary)")
        lines.append("")
        if reasoning:
            lines.append(reasoning)
        else:
            lines.append(
                "The automated review reached a preliminary coverage outcome based on "
                "the available evidence and policy material."
            )

    lines += ["", "---", "", "## 8. Payment Recommendation", ""]
    if payout:
        lines += [
            f"### Indicative payment: {payout}",
            "",
            "This figure is **indicative only**, before any excess or policy limits.",
        ]
    else:
        lines += [
            "### No payment recommended at this stage",
            "",
            "No reliable payment amount can be calculated from the available evidence.",
        ]
    if customer_estimate:
        lines += [
            "",
            f"**Customer repair estimate:** {customer_estimate} — **not** treated as an "
            "automated payment recommendation.",
        ]
    else:
        lines += [
            "",
            "**Customer repair estimate:** Not treated as an automated payment recommendation.",
        ]

    lines += [
        "",
        "---",
        "",
        "## 9. Assessor Action Required",
        "",
        "Please review the following before making the final claim decision:",
        "",
        "### ☐ 1. Verify the damage",
        "",
        "Confirm whether the photographs correspond to the claimant's vehicle and reported damage.",
        "",
        "### ☐ 2. Verify the incident",
        "",
        "Determine whether the available evidence supports the reported incident.",
        "",
        "### ☐ 3. Review policy coverage",
        "",
        f"Confirm whether the reported loss falls within the **{cover}** policy terms.",
        "",
        "### ☐ 4. Apply policy conditions",
        "",
        "Consider any applicable excess, exclusions, conditions or other requirements.",
        "",
    ]
    if fraud_reasons:
        lines += [
            "### ☐ 5. Investigate possible fraud",
            "",
            "Review the fraud alert above and confirm or clear the elevated risk before payment.",
            "",
            "### ☐ 6. Make final decision",
            "",
        ]
    else:
        lines += [
            "### ☐ 5. Make final decision",
            "",
        ]
    lines += [
        "**Approve / Amend / Decline / Request Further Information**",
        "",
        "---",
        "",
        "### Claim-AI Note",
        "",
        "This document is an **automated preliminary assessment** intended to assist the "
        "assessor. It does not constitute the final claim decision. The assessor remains "
        "responsible for reviewing the evidence, applying the policy, and making the "
        "final determination.",
    ]
    return "\n".join(lines)


def _llm_brief(facts: dict[str, Any]) -> str:
    decision_key = _decision_key(facts)
    fraud_score = _fraud_score(facts)
    payload = {
        "claim_reference": facts.get("claim_reference"),
        "customer_name": facts.get("customer_name"),
        "policy_number": facts.get("policy_number"),
        "coverage_type": facts.get("coverage_type"),
        "exact_customer_statement": _customer_exact_text(facts),
        "image_count": facts.get("image_count"),
        "damage_assessment": facts.get("damage"),
        "consistency": facts.get("consistency"),
        "preliminary_decision": decision_key,
        "fraud_alert": fraud_score >= _FRAUD_ALERT_THRESHOLD,
        "fraud_score": fraud_score,
        "fraud_reasons": _fraud_reasons(facts) if fraud_score >= _FRAUD_ALERT_THRESHOLD else [],
        "payment_allowed": _payment_allowed(facts),
        "suggested_payout": _indicative_payment(facts) or "",
        "customer_estimate": _money(facts.get("estimated_value")) or "",
        "policy_section": (facts.get("generation") or {}).get("cited_clause_ref"),
        "decision_reasoning": (facts.get("generation") or {}).get("reasoning")
        or (facts.get("ai_decision") or {}).get("reason_summary"),
    }
    response = get_gpt_client().responses.create(
        model=get_mini_deployment(),
        input=[
            {"role": "system", "content": _BRIEF_SYSTEM},
            {
                "role": "user",
                "content": "Write the Claim-AI preliminary decision brief from this JSON:\n"
                + json.dumps(payload, default=str),
            },
        ],
    )
    text = getattr(response, "output_text", None) or ""
    if not text.strip():
        raise RuntimeError("Empty brief from model")
    if decision_key in _NO_PAYOUT_DECISIONS and re.search(
        r"\$\s?\d|indicative payment:\s*\$", text, re.IGNORECASE
    ):
        if "no payment" not in text.lower():
            raise RuntimeError("LLM invented a payout on a no-payment decision")
    return text.strip()


async def build_assessor_decision_brief(claim_id: int, *, use_llm: bool = False) -> dict[str, Any]:
    """Build the scannable Claim-AI brief. Template is default for a consistent layout."""
    facts = _load_facts(claim_id)
    if facts is None:
        return {
            "claim_id": claim_id,
            "status": "not_found",
            "memo": "",
            "source": None,
        }

    ai = facts.get("ai_decision")
    if not ai:
        return {
            "claim_id": claim_id,
            "claim_reference": facts.get("claim_reference"),
            "status": "pending",
            "memo": (
                "# CLAIM-AI — PRELIMINARY DECISION BRIEF\n\n"
                "No automated decision is available yet. Once the customer submits the "
                "claim and the privacy-screened review completes, a decision brief will "
                "appear here."
            ),
            "source": "template",
        }

    memo = _template_brief(facts)
    source = "template"
    if use_llm and facts.get("pii_status") == "ready":
        try:
            polished = await asyncio.to_thread(_llm_brief, facts)
            if polished.lstrip().startswith("#"):
                memo = polished
                source = "llm"
        except Exception:
            pass

    # Assessor brief must show real values, not ADDRESS_2 / EMAIL_1 placeholders.
    session_id = facts.get("pii_session_id")
    mapping = load_pii_mapping_for_claim(claim_id, session_id)
    memo = rehydrate_assessor_text(
        memo, claim_id=claim_id, session_id=session_id, mapping=mapping
    )

    return {
        "claim_id": claim_id,
        "claim_reference": facts.get("claim_reference"),
        "status": "ready",
        "memo": memo,
        "source": source,
        "preliminary_decision": ai.get("decision"),
        "indicative_payment": _indicative_payment(facts),
        "fraud_alert": _fraud_score(facts) >= _FRAUD_ALERT_THRESHOLD,
        "fraud_score": round(_fraud_score(facts), 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
