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
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

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

CLAIM_TYPES = (
    ("damage", "Damage"),
    ("theft", "Theft"),
    ("loss", "Loss"),
    ("accident", "Accident"),
    ("water_damage", "Water damage"),
    ("fire", "Fire"),
    ("other", "Other"),
)
CLAIM_TYPE_VALUES = {value for value, _label in CLAIM_TYPES}

CLAIM_FORM_COLUMNS: dict[str, str] = {
    "claim_type": "VARCHAR(50)",
    "incident_date": "DATE",
    "incident_time": "VARCHAR(8)",
    "incident_location": "TEXT",
    "incident_description": "TEXT",
    "loss_description": "TEXT",
    "estimated_value": "NUMERIC(12, 2)",
    "property_damaged": "BOOLEAN",
    "claimant_name": "VARCHAR(100)",
    "claimant_email": "VARCHAR(100)",
    "claimant_phone": "VARCHAR(20)",
    "others_involved": "BOOLEAN",
    "other_party_name": "VARCHAR(100)",
    "other_party_phone": "VARCHAR(20)",
    "other_party_email": "VARCHAR(100)",
    "other_party_address": "TEXT",
    "other_party_vehicle_reg": "VARCHAR(20)",
    "other_party_insurer": "VARCHAR(100)",
    "police_involved": "BOOLEAN",
    "police_report_number": "VARCHAR(50)",
    "police_station": "VARCHAR(100)",
    "additional_comments": "TEXT",
    "declaration_accepted": "BOOLEAN DEFAULT FALSE",
    "declaration_name": "VARCHAR(100)",
    "declaration_date": "DATE",
}


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


def form_options() -> dict[str, list[dict[str, str]]]:
    return {
        "claim_types": [{"value": value, "label": label} for value, label in CLAIM_TYPES],
    }


def ensure_claim_form_columns() -> None:
    """Add claimant-form columns to existing databases. create_all does not alter tables."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for name, ddl in CLAIM_FORM_COLUMNS.items():
                cur.execute(f"ALTER TABLE claim ADD COLUMN IF NOT EXISTS {name} {ddl}")
        conn.commit()
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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = sanitize_free_text(value).strip()
    return text or None


def _parse_bool(value: str | None) -> bool | None:
    if value is None or not str(value).strip():
        return None
    lowered = str(value).strip().lower()
    if lowered in {"yes", "true", "1", "on"}:
        return True
    if lowered in {"no", "false", "0", "off"}:
        return False
    raise ClaimSubmitError("Use Yes or No for the yes/no questions.")


def _parse_date(value: str | None, *, label: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ClaimSubmitError(f"{label} must be a valid date.")


def _parse_time(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ClaimSubmitError("Approximate time must be HH:MM.")


def _parse_money(value: str | None) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ClaimSubmitError("Estimated value must be a number.") from exc
    if amount < 0:
        raise ClaimSubmitError("Estimated value cannot be negative.")
    return amount


def _usable_files(files: list[UploadFile] | None) -> list[UploadFile]:
    return [file for file in (files or []) if file.filename]


def _require(value: Any, label: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ClaimSubmitError(f"{label} is required.")


def _form_values(payload: dict[str, Any]) -> dict[str, Any]:
    claim_type = _clean(payload.get("claim_type"))
    if claim_type and claim_type not in CLAIM_TYPE_VALUES:
        raise ClaimSubmitError("Choose a valid claim type.")

    others_involved = _parse_bool(payload.get("others_involved"))
    police_involved = _parse_bool(payload.get("police_involved"))
    values = {
        "claim_type": claim_type,
        "incident_date": _parse_date(payload.get("incident_date"), label="Date of incident"),
        "incident_time": _parse_time(payload.get("incident_time")),
        "incident_location": _clean(payload.get("incident_location")),
        "incident_description": _clean(payload.get("incident_description") or payload.get("description")),
        "loss_description": _clean(payload.get("loss_description")),
        "estimated_value": _parse_money(payload.get("estimated_value")),
        "property_damaged": _parse_bool(payload.get("property_damaged")),
        "claimant_name": _clean(payload.get("claimant_name")),
        "claimant_email": _clean(payload.get("claimant_email")),
        "claimant_phone": _clean(payload.get("claimant_phone")),
        "others_involved": others_involved,
        "other_party_name": _clean(payload.get("other_party_name")),
        "other_party_phone": _clean(payload.get("other_party_phone")),
        "other_party_email": _clean(payload.get("other_party_email")),
        "other_party_address": _clean(payload.get("other_party_address")),
        "other_party_vehicle_reg": _clean(payload.get("other_party_vehicle_reg")),
        "other_party_insurer": _clean(payload.get("other_party_insurer")),
        "police_involved": police_involved,
        "police_report_number": _clean(payload.get("police_report_number")),
        "police_station": _clean(payload.get("police_station")),
        "additional_comments": _clean(payload.get("additional_comments")),
        "declaration_accepted": _parse_bool(payload.get("declaration_accepted")) or False,
        "declaration_name": _clean(payload.get("declaration_name")),
        "declaration_date": _parse_date(payload.get("declaration_date"), label="Declaration date"),
    }
    if others_involved is not True:
        for key in (
            "other_party_name",
            "other_party_phone",
            "other_party_email",
            "other_party_address",
            "other_party_vehicle_reg",
            "other_party_insurer",
        ):
            values[key] = None
    if police_involved is not True:
        values["police_report_number"] = None
        values["police_station"] = None
    return values


def _validate_submit(policy_id: int | None, values: dict[str, Any]) -> None:
    _require(policy_id, "Policy")
    _require(values["claim_type"], "Claim type")
    _require(values["incident_date"], "Date of incident")
    _require(values["incident_location"], "Location")
    _require(values["incident_description"], "What happened")
    _require(values["claimant_name"], "Full name")
    _require(values["claimant_email"], "Email address")
    _require(values["claimant_phone"], "Phone number")
    if values["others_involved"] is None:
        raise ClaimSubmitError("Say whether anyone else was involved.")
    if not values["declaration_accepted"]:
        raise ClaimSubmitError("Confirm the declaration before submitting.")
    _require(values["declaration_name"], "Declaration name")
    if values["declaration_date"] is None:
        values["declaration_date"] = date.today()


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
        db.add(
            ClaimDocument(
                claim_id=claim_id,
                file_type=file.content_type,
                file_url=blob_name,
            )
        )
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
    values = _form_values(payload)
    usable_files = _usable_files(files)

    if as_draft:
        _require(policy_id, "Policy")
        status = ClaimStatus.DRAFT.value
    else:
        _validate_submit(policy_id, values)
        status = ClaimStatus.SUBMITTED.value

    customer_id = int(user["sub"])
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

    uploaded = await _store_files(db, claim.claim_id, usable_files)
    await db.commit()
    await db.refresh(claim)

    return {
        "claim_id": claim.claim_id,
        "claim_reference": claim.claim_reference,
        "status": claim.status,
        "files_uploaded": uploaded,
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
