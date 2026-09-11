"""Manual test for Call 2 — Consistency Check.

Requires: the claim already has a Call 1 assessment (run
test_damage_assessment.py first), Azure login active for Foundry.

Run from backend/:
    python scripts/test_consistency_check.py <claim_id>
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import AsyncSessionLocal
from app.services.consistency_check_service import check_consistency


async def main(claim_id: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await check_consistency(claim_id, db)
        print("consistency_flag:", result.consistency_flag)
        print("discrepancies:", result.discrepancies)
        print("reasoning:", result.reasoning)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    claim_id = int(sys.argv[1]) if len(sys.argv) > 1 else 14  # default: the test claim
    asyncio.run(main(claim_id))
