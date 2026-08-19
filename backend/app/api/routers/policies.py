"""JSON policies API. Vue will call these when submitting a claim."""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_claimant
from app.api.schemas.responses import PolicyOut
from app.services.claim_service import list_policies

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/", response_model=list[PolicyOut])
def policies(_user: dict = Depends(require_claimant)) -> list[PolicyOut]:
    return [PolicyOut(**row) for row in list_policies()]
