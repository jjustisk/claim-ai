"""Claim form pre-fill from the customer's account and parsed policy schedule.

Returns only form fields we could read with confidence; anything missing is
left for the customer to enter.
"""

from __future__ import annotations

import re
from typing import Any

from app.connectors.db import get_sync_connection

STATE_ABBREVIATIONS = {
    "australian capital territory": "ACT",
    "new south wales": "NSW",
    "northern territory": "NT",
    "queensland": "QLD",
    "south australia": "SA",
    "tasmania": "TAS",
    "victoria": "VIC",
    "western australia": "WA",
}
_STATE_CODES = set(STATE_ABBREVIATIONS.values())

# "14 Banksia Avenue, Joondalup WA 6027" / "3/22 Smith St, Perth, WA 6000"
_ADDRESS_RE = re.compile(
    r"^\s*(?P<number>[\w/-]*\d[\w/-]*)\s+(?P<street>[^,]+?)\s*,\s*(?P<suburb>[^,]+?)\s*,?\s+"
    r"(?P<state>ACT|NSW|NT|QLD|SA|TAS|VIC|WA)\s+(?P<postcode>\d{4})\s*$",
    re.IGNORECASE,
)
_SAMPLE_SUFFIX_RE = re.compile(r"\s*\(sample\)\s*$", re.IGNORECASE)
_CAR_BODIES = {"suv", "hatchback", "sedan", "wagon", "ute", "coupe", "convertible", "van", "people mover"}


def state_code(value: str | None) -> str:
    """Return the state abbreviation for a full or abbreviated state name, or ''."""
    text = str(value or "").strip()
    if text.upper() in _STATE_CODES:
        return text.upper()
    return STATE_ABBREVIATIONS.get(text.lower(), "")


def parse_address(value: str | None) -> dict[str, str]:
    """Split a one-line Australian address into the form's address fields."""
    match = _ADDRESS_RE.match(str(value or ""))
    if not match:
        return {}
    return {
        "street_number": match["number"],
        "street_name": match["street"],
        "suburb": match["suburb"],
        "state": match["state"].upper(),
        "postcode": match["postcode"],
    }


def _schedule_fields(schedule: dict[str, Any] | None) -> dict[str, str]:
    """Flatten the schedule's two-column label/value rows into {label: value}."""
    fields: dict[str, str] = {}
    for table in (schedule or {}).get("tables") or []:
        for row in (table.get("rows") or [])[1:]:
            if len(row) >= 2 and row[0] and row[1]:
                label = " ".join(str(row[0]).split()).lower()
                fields.setdefault(label, " ".join(str(row[1]).split()))
    return fields


def _clean(value: str | None) -> str:
    return _SAMPLE_SUFFIX_RE.sub("", str(value or "")).strip()


def _vehicle_fields(fields: dict[str, str]) -> dict[str, str]:
    vehicle = _clean(fields.get("vehicle"))
    if not vehicle:
        return {}
    out: dict[str, str] = {}
    parts = vehicle.split()
    if parts and re.fullmatch(r"(19|20)\d{2}", parts[0]):
        out["vehicle_year"] = parts.pop(0)
    year = _clean(fields.get("year"))
    if re.fullmatch(r"(19|20)\d{2}", year):
        out["vehicle_year"] = year
    if parts:
        out["vehicle_make"] = parts[0]
    if len(parts) > 1:
        out["vehicle_model"] = " ".join(parts[1:])
    rego = _clean(fields.get("registration"))
    if rego:
        out["vehicle_registration"] = rego
    body = _clean(fields.get("body type")).lower()
    if body in _CAR_BODIES:
        out["vehicle_type"] = "Car"
    elif "motorcycle" in body:
        out["vehicle_type"] = "Motorcycle"
    elif "caravan" in body:
        out["vehicle_type"] = "Caravan"
    return out


def _holder_address(address: dict[str, str]) -> dict[str, str]:
    return {f"holder_{key}": value for key, value in address.items()}


def get_policy_prefill(policy_id: int, customer_id: int) -> dict[str, Any] | None:
    """Return claim-form values for one of the customer's policies, or None if not theirs."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.name, c.email, c.phone, c.address, p.schedule_details, pr.insurance_type
                FROM policy p
                JOIN customer c ON c.customer_id = p.customer_id
                LEFT JOIN product pr ON pr.product_id = p.product_id
                WHERE p.policy_id = %s AND p.customer_id = %s
                """,
                (policy_id, customer_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None

    name, email, phone, account_address, schedule, insurance_type = row
    fields = _schedule_fields(schedule)
    values: dict[str, str] = {}

    first, _, last = str(name or "").strip().partition(" ")
    if first:
        values["holder_first_name"] = first
    if last:
        values["holder_last_name"] = last.strip()
    if email:
        values["holder_email"] = email
    if phone:
        values["holder_phone"] = phone

    insured_address = parse_address(fields.get("insured address"))
    holder_address = parse_address(account_address) or insured_address
    values.update(_holder_address(holder_address))
    if not values.get("holder_state"):
        state = state_code(fields.get("state / territory"))
        if state:
            values["holder_state"] = state

    if insurance_type == "motor":
        values.update(_vehicle_fields(fields))

    return {
        "policy_id": policy_id,
        "insurance_type": insurance_type,
        "values": values,
        "insured_address": insured_address or None,
    }
