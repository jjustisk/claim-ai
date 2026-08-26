"""JSON claims API. Vue will call these; the test UI in pages/ is temporary."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_assessor, require_claimant
from app.api.schemas.responses import ClaimFormOptions, ClaimListOut, ClaimSubmitOut, ReviewIn
from app.connectors.db import get_db
from app.services.assessor_service import (
    ReviewError,
    claim_counts,
    download_claim_document,
    evidence_download_response,
    get_claim,
    list_claims,
    save_review,
)
from app.services.claim_form import payload_from_form
from app.services.claim_service import (
    ClaimSubmitError,
    customer_owns_claim_document,
    delete_customer_draft,
    form_options,
    get_customer_claim,
    list_customer_claims,
    submit_claim,
)

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("/form-options", response_model=ClaimFormOptions)
def claim_form_options(_user: dict = Depends(require_claimant)) -> ClaimFormOptions:
    return ClaimFormOptions(**form_options())


@router.get("/mine")
def my_claims(user: dict = Depends(require_claimant)) -> list[dict]:
    return jsonable_encoder(list_customer_claims(int(user["sub"])))


@router.get("/mine/{claim_id}")
def my_claim_detail(claim_id: int, user: dict = Depends(require_claimant)) -> dict:
    claim = get_customer_claim(claim_id, int(user["sub"]))
    if claim is None:
        raise HTTPException(404, "Claim not found.")
    return jsonable_encoder(claim)


@router.post("/", response_model=ClaimSubmitOut)
async def submit_claim_route(
    request: Request,
    user: dict = Depends(require_claimant),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    payload = payload_from_form(form)
    policy_raw = form.get("policy_id")
    intent = str(form.get("intent") or "submit")
    claim_id_raw = form.get("claim_id")
    try:
        policy_id = int(str(policy_raw)) if policy_raw not in (None, "") else None
        claim_id = int(str(claim_id_raw)) if claim_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(400, "Choose a valid policy.") from None
    if policy_id is None:
        raise HTTPException(400, "Policy is required.")
    upload_files = [item for item in form.getlist("files") if getattr(item, "filename", None)]
    try:
        return await submit_claim(
            db=db,
            user=user,
            policy_id=policy_id,
            files=upload_files,
            intent=intent,
            claim_id=claim_id,
            **payload,
        )
    except ClaimSubmitError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/counts")
def claims_counts(_user: dict = Depends(require_assessor)) -> dict[str, int]:
    return claim_counts()


@router.get("/", response_model=ClaimListOut)
def claims_index(
    status: str | None = None,
    _user: dict = Depends(require_assessor),
) -> ClaimListOut:
    return ClaimListOut(
        counts=claim_counts(),
        items=jsonable_encoder(list_claims(status)),
    )


@router.get("/{claim_id}")
def claim_detail(claim_id: int, _user: dict = Depends(require_assessor)) -> dict:
    claim = get_claim(claim_id)
    if claim is None:
        raise HTTPException(404, "Claim not found.")
    return jsonable_encoder(claim)


@router.delete("/{claim_id}")
async def delete_draft(claim_id: int, user: dict = Depends(require_claimant)) -> dict:
    try:
        return await delete_customer_draft(claim_id, int(user["sub"]))
    except ClaimSubmitError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{claim_id}/review")
def claim_review(
    claim_id: int,
    body: ReviewIn,
    user: dict = Depends(require_assessor),
) -> dict:
    if get_claim(claim_id) is None:
        raise HTTPException(404, "Claim not found.")
    try:
        save_review(int(user["sub"]), claim_id, body.outcome, body.notes)
    except ReviewError as exc:
        raise HTTPException(400, str(exc)) from exc
    claim = get_claim(claim_id)
    return jsonable_encoder(claim)


@router.get("/documents/{doc_id}")
async def download_document(
    doc_id: int,
    user: dict = Depends(get_current_user),
) -> Response:
    from azure.core.exceptions import ResourceNotFoundError

    role = user.get("role")
    if role == "claimant":
        if not customer_owns_claim_document(doc_id, int(user["sub"])):
            raise HTTPException(404, "Document not found.")
    elif role != "assessor":
        raise HTTPException(403, "Access denied.")

    try:
        downloaded = await download_claim_document(doc_id)
    except ResourceNotFoundError:
        raise HTTPException(404, "File not found in storage.") from None
    if downloaded is None:
        raise HTTPException(404, "Document not found.")
    data, filename, media_type = downloaded
    return evidence_download_response(data, filename, media_type)
