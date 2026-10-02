"""Looks up a comparable repair-cost range for the decision stage's
suggested_payout, so the model is anchored to a seeded range instead of
inventing a dollar figure from nothing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import RepairCostReference


async def lookup_repair_cost_range(
    db: AsyncSession, *, product: str, damage_type: str, severity: str
) -> dict | None:
    """Returns the matched row as a dict. Tries an exact damage_type
    match first, then falls back to the damage_type-agnostic row."""
    for dt in (damage_type, None):
        result = await db.execute(
            select(RepairCostReference).where(
                RepairCostReference.product == product,
                RepairCostReference.damage_type == dt,
                RepairCostReference.severity == severity,
            )
        )
        row = result.scalars().first()
        if row is not None:
            return {
                "cost_low": float(row.cost_low),
                "cost_high": float(row.cost_high),
                "unit": row.unit,
                "source": row.source,
                "matched_damage_type": dt,
            }
    return None


def format_repair_cost_range(reference: dict | None) -> str:
    """Formats a lookup result as a prompt-ready sentence, or a plain
    statement that no reference range was found."""
    if reference is None:
        return "No comparable repair cost reference available for this damage."
    return (
        f"Comparable repair cost range for this type of damage: "
        f"${reference['cost_low']:,.2f}-${reference['cost_high']:,.2f} {reference['unit'] or ''} "
        f"(source: {reference['source']}). Your suggested_payout should fall "
        f"within or near this range - explain any significant deviation."
    ).strip()


__all__ = ["lookup_repair_cost_range", "format_repair_cost_range"]
