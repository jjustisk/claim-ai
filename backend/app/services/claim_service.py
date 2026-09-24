"""Claim submission and claim-reference logic.

Creates claims, uploads supporting files, lists policies, and generates
reference codes like CLM-20260813-K7QX2M. The JSON API (and later Vue)
goes through this file instead of talking to storage or the database
on their own.
"""

from __future__ import annotations

import asyncio
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDocument, ClaimStatus
from app.connectors.db import get_sync_connection
from app.connectors.storage import upload_image
from app.services.image_similarity_service import IMAGE_FILE_TYPES, store_phash
from app.services.claim_form import (
    CLAIM_TYPES,
    ClaimSubmitError,
    attach_form_details,
    ensure_claim_form_columns,
    form_options,
    is_plausible_incident_model,
    parse_claim_form,
    save_form_children,
    validate_submit,
)
from app.services.notification_service import notify_claim_submitted

_REFERENCE_ALPHABET = string.ascii_uppercase + string.digits
_SUFFIX_LENGTH = 6

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB



def generate_claim_reference() -> str:
    """Build a reference like "CLM-20260813-K7QX2M".

    The date segment makes references sortable.
    Secrets are used to generate the random suffix to ensure uniqueness and unpredictability.
    """
    date_segment = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_SUFFIX_LENGTH))
    return f"CLM-{date_segment}-{suffix}"




def ensure_policy_customer_column() -> None:
    """Link policies to customers and backfill from existing claims where possible."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE policy
                ADD COLUMN IF NOT EXISTS customer_id INTEGER
                REFERENCES customer(customer_id)
                """
            )
            cur.execute(
                """
                UPDATE policy p
                SET customer_id = sub.customer_id
                FROM (
                    SELECT DISTINCT ON (policy_id) policy_id, customer_id
                    FROM claim
                    ORDER BY policy_id, claim_id
                ) sub
                WHERE p.policy_id = sub.policy_id
                  AND p.customer_id IS NULL
                """
            )
            cur.execute("DELETE FROM policy WHERE customer_id IS NULL")
            cur.execute("ALTER TABLE policy ALTER COLUMN customer_id SET NOT NULL")
        conn.commit()
    finally:
        conn.close()


def ensure_claim_document_phash_column() -> None:
    """Adds the perceptual-hash column used for image-similarity fraud scoring."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE claim_document ADD COLUMN IF NOT EXISTS phash bit(64)")
        conn.commit()
    finally:
        conn.close()


def customer_owns_policy(policy_id: int, customer_id: int) -> bool:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM policy
                WHERE policy_id = %s AND customer_id = %s
                """,
                (policy_id, customer_id),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def get_customer_profile(customer_id: int) -> dict[str, str | None]:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, email, phone
                FROM customer
                WHERE customer_id = %s
                """,
                (customer_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"name": None, "email": None, "phone": None}
            return {"name": row[0], "email": row[1], "phone": row[2]}
    finally:
        conn.close()


def get_customer_claim(claim_id: int, customer_id: int) -> dict[str, Any] | None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.*,
                    p.policy_id,
                    p.policy_number,
                    p.coverage_type
                FROM claim c
                JOIN policy p ON p.policy_id = c.policy_id
                WHERE c.claim_id = %s AND c.customer_id = %s
                """,
                (claim_id, customer_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            claim = dict(zip([col[0] for col in cur.description], row))
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
    finally:
        conn.close()
    return attach_form_details(claim)


def customer_owns_claim_document(doc_id: int, customer_id: int) -> bool:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM claim_document cd
                JOIN claim c ON c.claim_id = cd.claim_id
                WHERE cd.doc_id = %s AND c.customer_id = %s
                """,
                (doc_id, customer_id),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def list_policy_documents(policy_id: int, customer_id: int) -> list[dict[str, Any]]:
    """A policy's documents come from two places now: the product-level PDS
    (shared across every policy on that product) and this policy's own
    Policy Schedule row. See
    .claude/plans/stage0-pds-ingestion-retrieval.md."""
    if not customer_owns_policy(policy_id, customer_id):
        return []
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.pds_id, d.version, d.effective_date
                FROM pds_document d
                JOIN policy p ON p.product_id = d.product_id
                WHERE p.policy_id = %s AND d.version = 'PDS'
                UNION ALL
                SELECT pds_id, version, effective_date
                FROM pds_document
                WHERE policy_id = %s AND version = 'Policy Schedule'
                ORDER BY pds_id
                """,
                (policy_id, policy_id),
            )
            columns = [col[0] for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def get_policy_document(pds_id: int, customer_id: int) -> dict[str, Any] | None:
    """A document row is either product-scoped (PDS) or policy-scoped
    (Schedule) — join on whichever FK is set for this row."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.pds_id, p.policy_id, d.version, d.file_url, d.effective_date
                FROM pds_document d
                JOIN policy p ON (
                    (d.product_id IS NOT NULL AND p.product_id = d.product_id)
                    OR (d.policy_id IS NOT NULL AND p.policy_id = d.policy_id)
                )
                WHERE d.pds_id = %s AND p.customer_id = %s
                LIMIT 1
                """,
                (pds_id, customer_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return dict(zip([col[0] for col in cur.description], row))
    finally:
        conn.close()


def list_customer_claims(
    customer_id: int,
    status: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            c.claim_id,
            c.claim_reference,
            c.status,
            c.submission_date,
            c.claim_type,
            c.insurance_type,
            c.incident_date,
            c.incident_location,
            c.incident_description,
            c.claimant_name,
            c.claimant_phone,
            c.others_involved,
            p.policy_number
        FROM claim c
        JOIN policy p ON p.policy_id = c.policy_id
        WHERE c.customer_id = %s
    """
    params: tuple[Any, ...] = (customer_id,)
    if status:
        sql += " AND c.status = %s"
        params = (customer_id, status)
    sql += " ORDER BY c.claim_id DESC"

    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [col[0] for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()


async def delete_customer_draft(claim_id: int, customer_id: int) -> dict[str, Any]:
    """Remove a draft the claimant owns. Submitted claims cannot be deleted here."""
    claim = get_customer_claim(claim_id, customer_id)
    if claim is None or claim.get("status") != ClaimStatus.DRAFT.value:
        raise ClaimSubmitError("Only one of your drafts can be deleted.")

    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_url FROM claim_document WHERE claim_id = %s",
                (claim_id,),
            )
            blob_names = [row[0] for row in cur.fetchall() if row[0]]
            cur.execute("DELETE FROM claim_document WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM notification WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM claim_witness WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM claim_other_party WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM property_contents_item WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM motor_claim WHERE claim_id = %s", (claim_id,))
            cur.execute("DELETE FROM property_claim WHERE claim_id = %s", (claim_id,))
            cur.execute(
                """
                DELETE FROM claim
                WHERE claim_id = %s AND customer_id = %s AND status = %s
                """,
                (claim_id, customer_id, ClaimStatus.DRAFT.value),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise ClaimSubmitError("That draft could not be deleted.")
        conn.commit()
    finally:
        conn.close()

    from app.connectors.storage import delete_image

    for blob_name in blob_names:
        try:
            await delete_image(str(blob_name))
        except Exception:
            pass

    return {
        "claim_id": claim_id,
        "claim_reference": claim.get("claim_reference"),
        "deleted": True,
    }


def _usable_files(files: list[UploadFile] | None) -> list[UploadFile]:
    return [file for file in (files or []) if file.filename]


def _require(value: Any, label: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ClaimSubmitError(f"{label} is required.")


async def _store_files(db: AsyncSession, claim_id: int, files: list[UploadFile]) -> int:
    uploaded = 0
    for file in files:
        if file.content_type not in ALLOWED_TYPES:
            raise ClaimSubmitError(f"Unsupported file type: {file.content_type}")

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise ClaimSubmitError(f"File too large: {file.filename}")

        blob_name = f"claim-{claim_id}/{uuid.uuid4()}-{file.filename}"
        await upload_image(
            blob_name,
            contents,
            content_type=file.content_type,
            overwrite=False,
        )
        document = ClaimDocument(
            claim_id=claim_id,
            file_type=file.content_type,
            file_url=blob_name,
        )
        db.add(document)
        await db.flush()

        if file.content_type in IMAGE_FILE_TYPES:
            await store_phash(db, document.doc_id, contents)

        uploaded += 1
    return uploaded


async def submit_claim(
    *,
    db: AsyncSession,
    user: dict,
    policy_id: int | None,
    files: list[UploadFile] | None = None,
    intent: str = "submit",
    claim_id: int | None = None,
    **payload: Any,
) -> dict:
    as_draft = str(intent or "submit").strip().lower() == "draft"
    parsed = parse_claim_form(payload)
    values = parsed["claim"]
    usable_files = _usable_files(files)

    if as_draft:
        _require(policy_id, "Policy")
        status = ClaimStatus.DRAFT.value
    else:
        validate_submit(policy_id, parsed)  # includes the free heuristic plausibility check (Layer 1)
        # Layer 2 - only reached if Layer 1 already passed. Off the sync
        # validation path (asyncio.to_thread) so this blocking Foundry call
        # doesn't stall the event loop. Drafts skip both layers entirely -
        # a draft may be genuinely incomplete, not implausible.
        if not await asyncio.to_thread(is_plausible_incident_model, values["incident_description"]):
            raise ClaimSubmitError("Please provide a clearer description of what happened.")
        status = ClaimStatus.SUBMITTED.value

    customer_id = int(user["sub"])
    if policy_id is not None and not customer_owns_policy(int(policy_id), customer_id):
        raise ClaimSubmitError("Policy not found.")

    claim: Claim | None = None
    if claim_id is not None:
        claim = await db.get(Claim, claim_id)
        if claim is None or claim.customer_id != customer_id:
            raise ClaimSubmitError("Draft claim not found.")
        if claim.status != ClaimStatus.DRAFT.value:
            raise ClaimSubmitError("Only a draft can be updated.")

    if claim is None:
        claim = Claim(
            claim_reference=generate_claim_reference(),
            customer_id=customer_id,
            policy_id=int(policy_id),
        )
        db.add(claim)
        await db.flush()
    else:
        claim.policy_id = int(policy_id)

    claim.status = status
    if not as_draft:
        claim.submission_date = datetime.utcnow()
    for field, value in values.items():
        setattr(claim, field, value)
    if values["estimated_value"] is not None:
        claim.cost = values["estimated_value"]

    await save_form_children(db, claim, parsed)
    uploaded = await _store_files(db, claim.claim_id, usable_files)
    await db.commit()
    await db.refresh(claim)

    if not as_draft:
        await notify_claim_submitted(db, claim)

    return {
        "claim_id": claim.claim_id,
        "claim_reference": claim.claim_reference,
        "status": claim.status,
        "files_uploaded": uploaded,
    }


def list_policies(customer_id: int) -> list[dict[str, int | str | None]]:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT policy_id, policy_number, coverage_type
                FROM policy
                WHERE customer_id = %s
                ORDER BY policy_id
                LIMIT 50
                """,
                (customer_id,),
            )
            return [
                {
                    "policy_id": row[0],
                    "policy_number": row[1],
                    "coverage_type": row[2],
                }
                for row in cur.fetchall()
            ]
    finally:
        conn.close()
