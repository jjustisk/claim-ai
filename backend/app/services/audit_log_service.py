"""Per-stage audit trail entries, tied to a shared ai_decision row per claim.

get_or_create_decision(): whichever stage runs first for a claim creates a
"pending" ai_decision row; later stages reuse the same row, so every
stage's audit_log entry shares one decision_id without needing an
orchestrator to create the row up front.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import AIDecision, AuditLog

PENDING = "pending"


async def get_or_create_decision(db: AsyncSession, claim_id: int) -> AIDecision:
    result = await db.execute(
        select(AIDecision)
        .where(AIDecision.claim_id == claim_id, AIDecision.decision == PENDING)
        .order_by(AIDecision.created_at.desc())
        .limit(1)
    )
    existing = result.scalars().first()
    if existing is not None:
        return existing

    record = AIDecision(claim_id=claim_id, decision=PENDING)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def log_stage(
    db: AsyncSession,
    decision_id: int,
    stage_name: str,
    description: str,
    *,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    model_name: str | None = None,
) -> None:
    db.add(
        AuditLog(
            decision_id=decision_id,
            action_type=stage_name,
            description=description,
            input_payload=input_payload,
            output_payload=output_payload,
            model_name=model_name,
        )
    )
    await db.commit()
