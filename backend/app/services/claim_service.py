"""Claim submission and claim-reference logic.

Creates claims, uploads supporting files, lists policies, and generates
reference codes like CLM-20260813-K7QX2M. The JSON API (and later Vue)
goes through this file instead of talking to storage or the database
on their own.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDocument, ClaimStatus
from app.connectors.db import get_sync_connection
from app.connectors.storage import upload_image
from app.services.sanitization_service import sanitize_free_text

_REFERENCE_ALPHABET = string.ascii_uppercase + string.digits
_SUFFIX_LENGTH = 6

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


class ClaimSubmitError(Exception):
    """Raised when a claim cannot be submitted."""


def generate_claim_reference() -> str:
    """Build a reference like "CLM-20260813-K7QX2M".

    The date segment makes references sortable.
    Secrets are used to generate the random suffix to ensure uniqueness and unpredictability.
    """
    date_segment = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(_SUFFIX_LENGTH))
    return f"CLM-{date_segment}-{suffix}"


async def submit_claim(
    *,
    db: AsyncSession,
    user: dict,
    policy_id: int,
    description: str,
    files: list[UploadFile],
) -> dict:
    description = sanitize_free_text(description)

    claim = Claim(
        claim_reference=generate_claim_reference(),
        customer_id=int(user["sub"]),
        policy_id=policy_id,
        status=ClaimStatus.SUBMITTED.value,
    )
    db.add(claim)
    await db.flush()

    for file in files:
        if file.content_type not in ALLOWED_TYPES:
            raise ClaimSubmitError(f"Unsupported file type: {file.content_type}")

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise ClaimSubmitError(f"File too large: {file.filename}")

        blob_name = f"claim-{claim.claim_id}/{uuid.uuid4()}-{file.filename}"
        await upload_image(
            blob_name,
            contents,
            content_type=file.content_type,
            overwrite=False,
        )

        doc = ClaimDocument(
            claim_id=claim.claim_id,
            file_type=file.content_type,
            file_url=blob_name,
        )
        db.add(doc)

    await db.commit()
    await db.refresh(claim)

    return {
        "claim_id": claim.claim_id,
        "claim_reference": claim.claim_reference,
        "status": claim.status,
        "files_uploaded": len(files),
    }


def list_policies() -> list[dict[str, int | str | None]]:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT policy_id, policy_number, coverage_type
                FROM policy
                ORDER BY policy_id
                LIMIT 50
                """
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
