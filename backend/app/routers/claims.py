import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_claimant
from app.schema import Claim, ClaimDocument, ClaimStatus
from app.sanitization import sanitize_free_text
from app.claim_reference import generate_claim_reference
from app.storage import upload_image

router = APIRouter(prefix="/claims", tags=["claims"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


@router.post("/")
async def submit_claim(
    policy_id: int = Form(...),
    description: str = Form(...),
    files: list[UploadFile] = File(...),
    user: dict = Depends(require_claimant),
    db: AsyncSession = Depends(get_db),
):
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
            raise HTTPException(400, f"Unsupported file type: {file.content_type}")

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File too large: {file.filename}")

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