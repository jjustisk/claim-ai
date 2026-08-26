"""JSON policies API. Vue will call these when submitting a claim."""

from urllib.parse import unquote

from azure.core.exceptions import ResourceNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder

from app.api.dependencies import require_claimant
from app.api.schemas.responses import PolicyDocumentOut, PolicyOut
from app.services.assessor_service import evidence_download_response
from app.services.claim_service import (
    customer_owns_policy,
    get_policy_document,
    list_policies,
    list_policy_documents,
)
from app.connectors.storage import download_stored_blob

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/", response_model=list[PolicyOut])
def policies(user: dict = Depends(require_claimant)) -> list[PolicyOut]:
    return [PolicyOut(**row) for row in list_policies(int(user["sub"]))]


@router.get("/{policy_id}/documents", response_model=list[PolicyDocumentOut])
def policy_documents(
    policy_id: int,
    user: dict = Depends(require_claimant),
) -> list[PolicyDocumentOut]:
    customer_id = int(user["sub"])
    if not customer_owns_policy(policy_id, customer_id):
        raise HTTPException(404, "Policy not found.")
    return [PolicyDocumentOut(**row) for row in list_policy_documents(policy_id, customer_id)]


@router.get("/{policy_id}/documents/{pds_id}")
async def download_policy_document(
    policy_id: int,
    pds_id: int,
    user: dict = Depends(require_claimant),
) -> Response:
    customer_id = int(user["sub"])
    if not customer_owns_policy(policy_id, customer_id):
        raise HTTPException(404, "Policy not found.")

    doc = get_policy_document(pds_id, customer_id)
    if doc is None or int(doc["policy_id"]) != policy_id or not doc.get("file_url"):
        raise HTTPException(404, "Document not found.")

    try:
        data = await download_stored_blob(str(doc["file_url"]))
    except ResourceNotFoundError:
        raise HTTPException(404, "File not found in storage.") from None

    stored = str(doc["file_url"])
    filename = unquote(stored.rstrip("/").split("/")[-1]) or f"policy-{pds_id}.pdf"
    version = str(doc.get("version") or "document").lower().replace(" ", "-")
    if not filename.endswith(".pdf"):
        filename = f"{version}.pdf"
    return evidence_download_response(data, filename, "application/pdf")
