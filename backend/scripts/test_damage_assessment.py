"""Manual test for Call 1 — Damage Description.

Requires: DB reachable, a claim with real images already uploaded to
claim_document, Azure login active (az login) for Foundry.

Run from backend/:
    python scripts/test_damage_assessment.py <claim_id>
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import AsyncSessionLocal
from app.connectors.storage import close_blob_service_client
from app.services.damage_description_services import assess_damage


async def main(claim_id: int) -> None:
    async with AsyncSessionLocal() as db:
        assessment = await assess_damage(claim_id, db)
        print("images_assessable:", assessment.images_assessable)
        print("damage_description:", assessment.damage_description)
        print("reasoning:", assessment.reasoning)
        print("damage_type:", assessment.damage_type)
        print("severity:", assessment.severity)
        print("images:", assessment.images_assessed, "of", assessment.images_available)
    await close_blob_service_client()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    claim_id = int(sys.argv[1]) if len(sys.argv) > 1 else 14  # default: the test claim
    asyncio.run(main(claim_id))
