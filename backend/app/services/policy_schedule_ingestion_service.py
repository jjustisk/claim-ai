"""Parses a Policy Schedule PDF (a filled-in form, not narrative text) into
structured fields written directly onto the `policy` row — no chunking or
embedding, this is exact key-value data, not something to vector-search.

One-time, offline: run per policy via scripts/ingest_pds_documents.py. See
.claude/plans/stage0-pds-ingestion-retrieval.md for the design.

`excess`/`max_payout` extraction below is best-effort: it scans every table
row for a handful of known labels ("Basic excess", "Legal liability limit",
"Building Sum Insured", "Contents Sum Insured"). Everything else extracted
from the schedule's tables is kept in `schedule_details` for completeness,
without trying to normalise every possible field across motor vs. home
schedules into typed columns.
"""

from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation

import pdfplumber

_CURRENCY = re.compile(r"[\d,]+(?:\.\d+)?")
_SPECIAL_EXCESS_SEGMENT = re.compile(r"([A-Za-z][A-Za-z /]*?)\s*\$[\d,]+(?:\.\d+)?")


def _parse_currency(value: str) -> Decimal | None:
    match = _CURRENCY.search(value or "")
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def extract_schedule_fields(pdf_bytes: bytes) -> dict:
    """Return {"excess": Decimal|None, "max_payout": Decimal|None,
    "schedule_details": {...}} parsed from a Schedule PDF's tables."""
    tables: list[dict] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            for table_index, table in enumerate(page.find_tables()):
                data = table.extract()
                if not data:
                    continue
                tables.append(
                    {
                        "page": page_index + 1,
                        "table": table_index,
                        "rows": [
                            [str(cell or "").strip() for cell in row] for row in data
                        ],
                    }
                )

    excess: Decimal | None = None
    building_sum: Decimal | None = None
    contents_sum: Decimal | None = None
    liability_limit: Decimal | None = None

    for entry in tables:
        for row in entry["rows"]:
            if len(row) < 2:
                continue
            label = row[0].strip().lower()
            value = row[1]
            if label == "basic excess" and excess is None:
                excess = _parse_currency(value)
            elif "legal liability" in label and liability_limit is None:
                liability_limit = _parse_currency(value)
            elif "building sum insured" in label and building_sum is None:
                building_sum = _parse_currency(value)
            elif "contents sum insured" in label and contents_sum is None:
                contents_sum = _parse_currency(value)

    # Sum insured (Building/Contents) bounds first-party property-damage
    # payouts — the common case for a claim — so it takes priority over the
    # legal liability limit, which bounds third-party liability instead and
    # would badly overstate a property claim's ceiling if picked first
    # (e.g. Home schedules carry both a ~$1M sum insured and a separate
    # $20M liability figure; motor schedules mostly only have liability).
    if building_sum is not None or contents_sum is not None:
        max_payout = (building_sum or Decimal(0)) + (contents_sum or Decimal(0))
    elif liability_limit is not None:
        max_payout = liability_limit
    else:
        max_payout = None

    return {
        "excess": excess,
        "max_payout": max_payout,
        "schedule_details": {"tables": tables},
    }


def parse_scenario_excesses(schedule_details: dict | None) -> dict[str, Decimal]:
    """Best-effort {label: amount} for every excess line item in a
    schedule's tables, not just "Basic excess" - both the one-excess-per-row
    motor format (Excess | Amount | When it may apply) and home's "Special
    excesses" row, which packs several "Label $amount" segments into one
    semicolon-separated cell (e.g. "Flood $1,500; storm $1,000").
    """
    excesses: dict[str, Decimal] = {}
    for entry in (schedule_details or {}).get("tables", []):
        for row in entry["rows"]:
            if len(row) < 2:
                continue
            label, value = row[0].strip().lower(), row[1]
            if label == "special excesses":
                for segment in value.split(";"):
                    match = _SPECIAL_EXCESS_SEGMENT.search(segment)
                    amount = _parse_currency(segment)
                    if match and amount is not None:
                        excesses[match.group(1).strip().lower()] = amount
            elif label.endswith("excess") and label not in excesses:
                amount = _parse_currency(value)
                if amount is not None:
                    excesses[label] = amount
    return excesses
