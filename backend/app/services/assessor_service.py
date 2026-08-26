"""Assessor review logic.

Loads the claims queue, claim detail, saves an outcome, and downloads
evidence. Used by the JSON API (what Vue will call). The HTML test UI
in pages/ also uses these helpers until Vue replaces it.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote

from fastapi.responses import Response

from app.api.schemas import ClaimStatus
from app.connectors.db import get_sync_connection
from app.connectors.storage import download_stored_blob
from app.services.claim_form import attach_form_details
from app.services.sanitization_service import sanitize_free_text

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
                SELECT decision_id, decision, confidence_score, reason_summary, created_at
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
    finally:
        conn.close()
    return attach_form_details(claim)


def save_review(assessor_id: int, claim_id: int, outcome: str, notes: str) -> None:
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


def evidence_download_response(data: bytes, filename: str, media_type: str | None) -> Response:
    safe = filename.replace("\\", "_").replace('"', "").replace("\r", "").replace("\n", "")
    ascii_name = safe.encode("ascii", "replace").decode("ascii") or "document"
    return Response(
        content=data,
        media_type=media_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
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
