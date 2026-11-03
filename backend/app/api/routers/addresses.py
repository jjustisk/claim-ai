"""Address autocomplete for the claim form."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_claimant
from app.services.address_service import search_addresses

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("/search")
async def address_search(
    q: str = Query(..., min_length=3, max_length=120),
    _user: dict = Depends(require_claimant),
) -> list[dict[str, str]]:
    return await search_addresses(q)
