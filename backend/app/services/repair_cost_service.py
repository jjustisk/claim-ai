"""Small repair price list used to price the repair behind a payout recommendation.

The model picks items and quantities from the list and code multiplies them out, so every
dollar in the repair estimate can be traced to a line. Prices live in app/data/repair_costs.json.
"""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

PRICE_FILE = Path(__file__).resolve().parents[1] / "data" / "repair_costs.json"
MAX_QUANTITY = 500


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    return json.loads(PRICE_FILE.read_text(encoding="utf-8"))


def price_list(product: str | None = None) -> list[dict[str, Any]]:
    """Items for one product ('property' or 'motor'), or every item when product is None."""
    return [item for item in _load()["items"] if product is None or item["product"] == product]


def prompt_block(product: str | None) -> list[str]:
    """Lines listing the available items for the decision prompt. Prices are deliberately not shown."""
    items = price_list(product)
    if not items:
        return ["(no price list for this product)"]
    return [f"- {item['id']}: {item['label']} ({item['unit']})" for item in items]


def price_repairs(product: str | None, requested: list[Any]) -> dict[str, Any]:
    """Price the items the model asked for. Unknown ids are reported, not guessed at."""
    by_id = {item["id"]: item for item in price_list(product)}
    quantities: dict[str, Decimal] = {}
    unknown: list[str] = []
    for request in requested:
        item_id = str(getattr(request, "item_id", "")).strip()
        quantity = Decimal(str(getattr(request, "quantity", 0) or 0))
        if item_id not in by_id:
            if item_id:
                unknown.append(item_id)
            continue
        if quantity <= 0:
            continue
        quantities[item_id] = min(quantities.get(item_id, Decimal(0)) + quantity, Decimal(MAX_QUANTITY))

    lines = []
    total = Decimal(0)
    for item_id, quantity in quantities.items():
        item = by_id[item_id]
        unit_cost = Decimal(str(item["unit_cost"]))
        line_total = unit_cost * quantity
        total += line_total
        lines.append({
            "item_id": item_id,
            "label": item["label"],
            "unit": item["unit"],
            "quantity": float(quantity),
            "unit_cost": float(unit_cost),
            "total": float(line_total),
        })
    return {"lines": lines, "total": float(total), "unknown_items": unknown}
