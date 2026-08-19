"""JSON claims API. Vue will call these; the test UI in pages/ is temporary."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_assessor, require_claimant
from app.api.schemas.responses import ClaimListOut, ClaimSubmitOut, ReviewIn
from app.connectors.db import get_db
from app.services.assessor_service import (
    ReviewError,
    claim_counts,
    download_claim_document,
    get_claim,
    list_claims,
    save_review,
)
from app.services.claim_service import ClaimSubmitError, submit_claim

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/", response_model=ClaimSubmitOut)
async def submit_claim_route(
    policy_id: int = Form(...),
    description: str = Form(...),
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_claimant),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await submit_claim(
            db=db,
            user=user,
            policy_id=policy_id,
            description=description,
            files=files,
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
    _user: dict = Depends(require_assessor),
) -> Response:
    downloaded = await download_claim_document(doc_id)
    if downloaded is None:
        raise HTTPException(404, "Document not found.")
    data, filename, media_type = downloaded
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
