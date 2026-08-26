"""Allianz motor and property claim-form constants, parsing, and table setup."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import (
    Claim,
    ClaimOtherParty,
    ClaimWitness,
    MotorClaim,
    PropertyClaim,
    PropertyContentsItem,
)
from app.connectors.db import get_sync_connection
from app.services.sanitization_service import sanitize_free_text

INSURANCE_TYPES = (
    ("motor", "Motor vehicle"),
    ("property", "Property"),
)
INSURANCE_TYPE_VALUES = {value for value, _label in INSURANCE_TYPES}

TITLES = ("Mr", "Mrs", "Ms", "Miss", "Other")
STATES = ("ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA", "NZ")
CONTACT_METHODS = ("SMS", "Email", "Phone")
MOTOR_RELATIONSHIPS = ("Broker", "Authorised Representative", "Nominated Driver", "Other")
PROPERTY_RELATIONSHIPS = ("Insured", "Broker", "Authorised Representative", "Other")
VEHICLE_TYPES = ("Car", "Caravan", "Motorcycle", "Other")

PROPERTY_CLAIM_TYPES = (
    ("storm_hail_water", "Storm, hail or water damage"),
    ("cyclone", "Cyclone"),
    ("burglary_theft", "Burglary or theft"),
    ("accidental", "Accidental loss or damage"),
    ("glass", "Breakage of glass"),
    ("motor_burnout", "Electric motor burnout"),
    ("impact_malicious", "Impact or malicious damage"),
    ("fire", "Fire damage"),
    ("other", "Other"),
)
PROPERTY_CLAIM_TYPE_VALUES = {value for value, _label in PROPERTY_CLAIM_TYPES}

# Kept so older submitted rows still display a label.
LEGACY_CLAIM_TYPES = (
    ("damage", "Damage"),
    ("theft", "Theft"),
    ("loss", "Loss"),
    ("accident", "Accident"),
    ("water_damage", "Water damage"),
    ("fire", "Fire"),
    ("other", "Other"),
)
CLAIM_TYPES = INSURANCE_TYPES
CLAIM_TYPE_VALUES = INSURANCE_TYPE_VALUES | PROPERTY_CLAIM_TYPE_VALUES | {
    value for value, _label in LEGACY_CLAIM_TYPES
}

VEHICLE_DAMAGE_AREAS = (
    "No panels damaged",
    "All panels damaged",
    "Passenger side",
    "Passenger rear",
    "Passenger front",
    "Driver side",
    "Driver rear",
    "Driver front",
    "Rear end",
    "Front end",
    "Bonnet",
    "Roof",
    "Interior",
    "Undercarriage",
    "Engine",
    "Burnt",
    "Stripped",
    "Signwriting / Wrapping",
    "Windscreen / window glass",
)

BUILDING_AREAS = (
    "Bathroom",
    "Bedroom",
    "Dining room",
    "Lounge / family room",
    "Kitchen",
    "Laundry",
    "Toilet",
    "Garage / Shed",
    "Roof",
    "Fence",
    "Swimming Pool",
    "Entire property",
    "Other",
)

CONTENTS_CATEGORIES = (
    ("appliances", "Appliances"),
    ("bicycles", "Bicycles"),
    ("carpets", "Carpets"),
    ("cash", "Cash"),
    ("clothing", "Clothing / personal items"),
    ("computers", "Computers"),
    ("curtains", "Curtains / blinds"),
    ("electronics", "Electronics"),
    ("furniture", "Furniture"),
    ("jewellery", "Jewellery"),
    ("mobile_devices", "Mobile devices"),
    ("outdoor_furniture", "Outdoor furniture"),
    ("sporting_equipment", "Sporting equipment"),
    ("tools", "Tools"),
    ("other", "Other"),
)

CLAIM_FORM_COLUMNS: dict[str, str] = {
    "claim_type": "VARCHAR(50)",
    "insurance_type": "VARCHAR(20)",
    "incident_date": "DATE",
    "incident_time": "VARCHAR(8)",
    "incident_location": "TEXT",
    "incident_description": "TEXT",
    "loss_description": "TEXT",
    "estimated_value": "NUMERIC(12, 2)",
    "property_damaged": "BOOLEAN",
    "claimant_name": "VARCHAR(100)",
    "claimant_email": "VARCHAR(100)",
    "claimant_phone": "VARCHAR(20)",
    "others_involved": "BOOLEAN",
    "other_party_name": "VARCHAR(100)",
    "other_party_phone": "VARCHAR(20)",
    "other_party_email": "VARCHAR(100)",
    "other_party_address": "TEXT",
    "other_party_vehicle_reg": "VARCHAR(20)",
    "other_party_insurer": "VARCHAR(100)",
    "police_involved": "BOOLEAN",
    "police_report_number": "VARCHAR(50)",
    "police_station": "VARCHAR(100)",
    "additional_comments": "TEXT",
    "declaration_accepted": "BOOLEAN DEFAULT FALSE",
    "declaration_name": "VARCHAR(100)",
    "declaration_date": "DATE",
    "holder_title": "VARCHAR(20)",
    "holder_first_name": "VARCHAR(100)",
    "holder_last_name": "VARCHAR(100)",
    "holder_company": "VARCHAR(150)",
    "holder_unit": "VARCHAR(20)",
    "holder_street_number": "VARCHAR(20)",
    "holder_street_name": "VARCHAR(150)",
    "holder_suburb": "VARCHAR(100)",
    "holder_state": "VARCHAR(10)",
    "holder_postcode": "VARCHAR(10)",
    "preferred_contact_method": "VARCHAR(20)",
    "alternate_phone": "VARCHAR(20)",
    "gst_registered": "BOOLEAN",
    "abn": "VARCHAR(20)",
    "gst_itc_percent": "VARCHAR(20)",
    "eft_account_name": "VARCHAR(150)",
    "eft_bsb": "VARCHAR(10)",
    "eft_account_number": "VARCHAR(20)",
    "incident_street": "VARCHAR(150)",
    "incident_cross_street": "VARCHAR(150)",
    "incident_suburb": "VARCHAR(100)",
    "incident_state": "VARCHAR(10)",
    "incident_postcode": "VARCHAR(10)",
    "is_policyholder": "BOOLEAN",
    "relationship_to_holder": "VARCHAR(50)",
    "reporter_reason": "TEXT",
    "witnesses_present": "BOOLEAN",
    "police_reported_date": "DATE",
    "charges_laid": "BOOLEAN",
    "charges_details": "TEXT",
    "declaration_position": "VARCHAR(100)",
}

MOTOR_CLAIM_COLUMNS: dict[str, str] = {
    "person_injured": "BOOLEAN",
    "vehicle_driven": "BOOLEAN",
    "policyholder_was_driver": "BOOLEAN",
    "driver_title": "VARCHAR(20)",
    "driver_first_name": "VARCHAR(100)",
    "driver_last_name": "VARCHAR(100)",
    "driver_dob": "DATE",
    "driver_phone": "VARCHAR(20)",
    "driver_email": "VARCHAR(100)",
    "driver_licence_number": "VARCHAR(50)",
    "driver_licence_years": "VARCHAR(20)",
    "driver_unit": "VARCHAR(20)",
    "driver_street_number": "VARCHAR(20)",
    "driver_street_name": "VARCHAR(150)",
    "driver_suburb": "VARCHAR(100)",
    "driver_state": "VARCHAR(10)",
    "driver_postcode": "VARCHAR(10)",
    "alcohol_or_drugs": "BOOLEAN",
    "alcohol_details": "TEXT",
    "vehicle_registration": "VARCHAR(20)",
    "vehicle_year": "VARCHAR(4)",
    "vehicle_make": "VARCHAR(50)",
    "vehicle_model": "VARCHAR(50)",
    "vehicle_type": "VARCHAR(30)",
    "vehicle_damage_areas": "TEXT",
    "vehicle_towed": "BOOLEAN",
    "vehicle_now_location": "TEXT",
    "airbags_deployed": "BOOLEAN",
    "speed_over_40": "BOOLEAN",
    "other_vehicle_involved": "BOOLEAN",
    "other_property_damaged": "BOOLEAN",
    "licence_cancelled_3yrs": "BOOLEAN",
    "cancelled_fine_defaults": "BOOLEAN",
    "convicted_alcohol_crime_3yrs": "BOOLEAN",
    "insurance_declined_5yrs": "BOOLEAN",
}

PROPERTY_CLAIM_COLUMNS: dict[str, str] = {
    "postal_same_as_insured": "BOOLEAN",
    "incident_at_insured_address": "BOOLEAN",
    "broker_name": "VARCHAR(150)",
    "broker_phone": "VARCHAR(20)",
    "notify_policyholder": "BOOLEAN",
    "building_damaged": "BOOLEAN",
    "building_areas": "TEXT",
    "bathroom_rooms": "VARCHAR(10)",
    "bedroom_rooms": "VARCHAR(10)",
    "lounge_rooms": "VARCHAR(10)",
    "damage_carpet": "TEXT",
    "damage_ceiling": "TEXT",
    "damage_floor": "TEXT",
    "damage_wall": "TEXT",
    "damage_windows": "TEXT",
    "damage_other": "TEXT",
    "property_secure": "BOOLEAN",
    "repairs_done": "BOOLEAN",
    "property_habitable": "BOOLEAN",
    "contents_affected": "BOOLEAN",
    "contents_total_value": "NUMERIC(12, 2)",
    "other_person_responsible": "BOOLEAN",
    "convicted_crime_5yrs": "BOOLEAN",
    "insurance_declined_5yrs": "BOOLEAN",
}


class ClaimSubmitError(Exception):
    """Raised when a claim cannot be submitted."""


def form_options() -> dict[str, list[dict[str, str]]]:
    return {
        "insurance_types": _option_list(INSURANCE_TYPES),
        "claim_types": _option_list(INSURANCE_TYPES),
        "property_claim_types": _option_list(PROPERTY_CLAIM_TYPES),
        "titles": _plain_options(TITLES),
        "states": _plain_options(STATES),
        "contact_methods": _plain_options(CONTACT_METHODS),
        "motor_relationships": _plain_options(MOTOR_RELATIONSHIPS),
        "property_relationships": _plain_options(PROPERTY_RELATIONSHIPS),
        "vehicle_types": _plain_options(VEHICLE_TYPES),
        "vehicle_damage_areas": _plain_options(VEHICLE_DAMAGE_AREAS),
        "building_areas": _plain_options(BUILDING_AREAS),
        "contents_categories": _option_list(CONTENTS_CATEGORIES),
    }


def insurance_type_label(value: Any) -> str:
    labels = {
        **dict(INSURANCE_TYPES),
        **dict(PROPERTY_CLAIM_TYPES),
        **dict(LEGACY_CLAIM_TYPES),
    }
    if value in labels:
        return labels[str(value)]
    return str(value or "—")


def claim_display_type(row: dict[str, Any]) -> str:
    insurance = row.get("insurance_type") or row.get("claim_type")
    label = insurance_type_label(insurance)
    extra = row.get("claim_type")
    if row.get("insurance_type") == "property" and extra and extra not in INSURANCE_TYPE_VALUES:
        return f"{label} — {insurance_type_label(extra)}"
    return label


def policy_matches_insurance_type(coverage_type: Any, insurance_type: str | None) -> bool:
    if not insurance_type:
        return True
    text = str(coverage_type or "").lower()
    if insurance_type == "motor":
        return "motor" in text or "vehicle" in text
    if insurance_type == "property":
        return any(token in text for token in ("home", "building", "contents", "property"))
    return True


def ensure_claim_form_columns() -> None:
    """Add claimant-form columns and type-specific tables. create_all does not alter tables."""
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for name, ddl in CLAIM_FORM_COLUMNS.items():
                cur.execute(f"ALTER TABLE claim ADD COLUMN IF NOT EXISTS {name} {ddl}")
            _create_child_table(cur, "motor_claim", MOTOR_CLAIM_COLUMNS)
            _create_child_table(cur, "property_claim", PROPERTY_CLAIM_COLUMNS)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_witness (
                    witness_id SERIAL PRIMARY KEY,
                    claim_id INTEGER NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL DEFAULT 1,
                    title VARCHAR(20),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    unit VARCHAR(20),
                    street_number VARCHAR(20),
                    street_name VARCHAR(150),
                    suburb VARCHAR(100),
                    state VARCHAR(10),
                    postcode VARCHAR(10),
                    phone VARCHAR(20),
                    email VARCHAR(100)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_other_party (
                    party_id SERIAL PRIMARY KEY,
                    claim_id INTEGER NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL DEFAULT 1,
                    title VARCHAR(20),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    company_name VARCHAR(150),
                    unit VARCHAR(20),
                    street_number VARCHAR(20),
                    street_name VARCHAR(150),
                    suburb VARCHAR(100),
                    state VARCHAR(10),
                    postcode VARCHAR(10),
                    phone VARCHAR(20),
                    email VARCHAR(100),
                    insurance_company VARCHAR(100),
                    insurance_policy_number VARCHAR(50),
                    insurance_claim_number VARCHAR(50),
                    licence_number VARCHAR(50),
                    vehicle_registration VARCHAR(20),
                    vehicle_year VARCHAR(4),
                    vehicle_make VARCHAR(50),
                    vehicle_model VARCHAR(50),
                    vehicle_type VARCHAR(30),
                    vehicle_damage_areas TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS property_contents_item (
                    item_id SERIAL PRIMARY KEY,
                    claim_id INTEGER NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
                    category VARCHAR(50) NOT NULL,
                    description TEXT,
                    estimated_value NUMERIC(12, 2)
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


def attach_form_details(claim: dict[str, Any]) -> dict[str, Any]:
    """Load motor/property child rows onto a claim dict."""
    claim_id = claim.get("claim_id")
    if claim_id is None:
        return claim
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            claim["motor"] = _fetch_one(cur, "SELECT * FROM motor_claim WHERE claim_id = %s", (claim_id,))
            claim["property"] = _fetch_one(cur, "SELECT * FROM property_claim WHERE claim_id = %s", (claim_id,))
            claim["witnesses"] = _fetch_all(
                cur,
                "SELECT * FROM claim_witness WHERE claim_id = %s ORDER BY sequence, witness_id",
                (claim_id,),
            )
            claim["other_parties"] = _fetch_all(
                cur,
                "SELECT * FROM claim_other_party WHERE claim_id = %s ORDER BY sequence, party_id",
                (claim_id,),
            )
            claim["contents_items"] = _fetch_all(
                cur,
                "SELECT * FROM property_contents_item WHERE claim_id = %s ORDER BY item_id",
                (claim_id,),
            )
    finally:
        conn.close()
    return flatten_claim_form(claim)


def flatten_claim_form(claim: dict[str, Any]) -> dict[str, Any]:
    """Copy child-table values onto top-level keys the HTML form expects."""
    out = dict(claim)
    for key in ("motor", "property"):
        child = claim.get(key) or {}
        for field, value in child.items():
            if field != "claim_id":
                out[field] = value
    for index, witness in enumerate(claim.get("witnesses") or [], start=1):
        for field, value in witness.items():
            if field in {"witness_id", "claim_id", "sequence"}:
                continue
            out[f"witness_{index}_{field}"] = value
    for index, party in enumerate(claim.get("other_parties") or [], start=1):
        for field, value in party.items():
            if field in {"party_id", "claim_id", "sequence"}:
                continue
            out[f"other_{index}_{field}"] = value
        damage = party.get("vehicle_damage_areas")
        if damage:
            out[f"other_{index}_vehicle_damage"] = [part.strip() for part in str(damage).split(",") if part.strip()]
    for item in claim.get("contents_items") or []:
        category = item.get("category")
        if not category:
            continue
        out[f"contents_{category}_description"] = item.get("description")
        out[f"contents_{category}_value"] = item.get("estimated_value")
    damage = out.get("vehicle_damage_areas")
    if isinstance(damage, str) and damage:
        out["vehicle_damage"] = [part.strip() for part in damage.split(",") if part.strip()]
    areas = out.get("building_areas")
    if isinstance(areas, str) and areas:
        out["building_area"] = [part.strip() for part in areas.split(",") if part.strip()]
    return out


def parse_claim_form(payload: dict[str, Any]) -> dict[str, Any]:
    insurance_type = _clean(payload.get("insurance_type") or payload.get("claim_type"))
    if insurance_type in PROPERTY_CLAIM_TYPE_VALUES:
        insurance_type = "property"
    if insurance_type and insurance_type not in INSURANCE_TYPE_VALUES:
        raise ClaimSubmitError("Choose motor vehicle or property insurance.")

    property_claim_type = _clean(payload.get("property_claim_type") or payload.get("claim_type"))
    if insurance_type == "motor":
        property_claim_type = None
    elif property_claim_type and property_claim_type not in PROPERTY_CLAIM_TYPE_VALUES:
        if property_claim_type not in INSURANCE_TYPE_VALUES:
            raise ClaimSubmitError("Choose a valid property claim type.")
        property_claim_type = None

    holder_first = _clean(payload.get("holder_first_name"))
    holder_last = _clean(payload.get("holder_last_name"))
    holder_name = " ".join(part for part in (holder_first, holder_last) if part) or _clean(payload.get("claimant_name"))
    holder_email = _clean(payload.get("holder_email") or payload.get("claimant_email"))
    holder_phone = _clean(payload.get("holder_phone") or payload.get("claimant_phone"))

    incident_street = _clean(payload.get("incident_street"))
    incident_suburb = _clean(payload.get("incident_suburb"))
    incident_state = _clean(payload.get("incident_state"))
    incident_postcode = _clean(payload.get("incident_postcode"))
    incident_location = _clean(payload.get("incident_location")) or _join_address(
        incident_street, incident_suburb, incident_state, incident_postcode
    )

    witnesses = _parse_people(payload, "witness", 2, WITNESS_FIELDS)
    other_parties = _parse_people(payload, "other", 2, OTHER_PARTY_FIELDS)
    first_other = other_parties[0] if other_parties else {}
    others_involved = _parse_bool(payload.get("others_involved"))
    if others_involved is None:
        if insurance_type == "motor":
            others_involved = _parse_bool(payload.get("other_vehicle_involved")) or _parse_bool(
                payload.get("other_property_damaged")
            )
        elif insurance_type == "property":
            others_involved = _parse_bool(payload.get("other_person_responsible"))
        if other_parties:
            others_involved = True

    gst_registered = _parse_bool(payload.get("gst_registered"))
    police_involved = _parse_bool(payload.get("police_involved"))
    is_policyholder = _parse_bool(payload.get("is_policyholder"))
    witnesses_present = _parse_bool(payload.get("witnesses_present"))

    claim_values = {
        "insurance_type": insurance_type,
        "claim_type": property_claim_type or insurance_type,
        "incident_date": _parse_date(payload.get("incident_date"), label="Date the incident occurred"),
        "incident_time": _parse_time(payload.get("incident_time")),
        "incident_location": incident_location,
        "incident_description": _clean(payload.get("incident_description") or payload.get("description")),
        "loss_description": _clean(payload.get("loss_description")),
        "estimated_value": _parse_money(payload.get("estimated_value") or payload.get("contents_total_value")),
        "property_damaged": _parse_bool(payload.get("building_damaged") or payload.get("property_damaged")),
        "claimant_name": holder_name,
        "claimant_email": holder_email,
        "claimant_phone": holder_phone,
        "others_involved": others_involved,
        "other_party_name": _join_name(first_other.get("first_name"), first_other.get("last_name"))
        or _clean(payload.get("other_party_name")),
        "other_party_phone": first_other.get("phone") or _clean(payload.get("other_party_phone")),
        "other_party_email": first_other.get("email") or _clean(payload.get("other_party_email")),
        "other_party_address": _join_address(
            first_other.get("street_name"),
            first_other.get("suburb"),
            first_other.get("state"),
            first_other.get("postcode"),
        ) or _clean(payload.get("other_party_address")),
        "other_party_vehicle_reg": first_other.get("vehicle_registration")
        or _clean(payload.get("other_party_vehicle_reg")),
        "other_party_insurer": first_other.get("insurance_company") or _clean(payload.get("other_party_insurer")),
        "police_involved": police_involved,
        "police_report_number": _clean(payload.get("police_report_number")),
        "police_station": _clean(payload.get("police_station")),
        "additional_comments": _clean(payload.get("additional_comments")),
        "declaration_accepted": _parse_bool(payload.get("declaration_accepted")) or False,
        "declaration_name": _clean(payload.get("declaration_name")) or holder_name,
        "declaration_date": _parse_date(payload.get("declaration_date"), label="Declaration date"),
        "holder_title": _clean(payload.get("holder_title")),
        "holder_first_name": holder_first,
        "holder_last_name": holder_last,
        "holder_company": _clean(payload.get("holder_company")),
        "holder_unit": _clean(payload.get("holder_unit")),
        "holder_street_number": _clean(payload.get("holder_street_number")),
        "holder_street_name": _clean(payload.get("holder_street_name")),
        "holder_suburb": _clean(payload.get("holder_suburb")),
        "holder_state": _clean(payload.get("holder_state")),
        "holder_postcode": _clean(payload.get("holder_postcode")),
        "preferred_contact_method": _clean(payload.get("preferred_contact_method")),
        "alternate_phone": _clean(payload.get("alternate_phone")),
        "gst_registered": gst_registered,
        "abn": _clean(payload.get("abn")),
        "gst_itc_percent": _clean(payload.get("gst_itc_percent")),
        "eft_account_name": _clean(payload.get("eft_account_name")),
        "eft_bsb": _clean(payload.get("eft_bsb")),
        "eft_account_number": _clean(payload.get("eft_account_number")),
        "incident_street": incident_street,
        "incident_cross_street": _clean(payload.get("incident_cross_street")),
        "incident_suburb": incident_suburb,
        "incident_state": incident_state,
        "incident_postcode": incident_postcode,
        "is_policyholder": is_policyholder,
        "relationship_to_holder": _clean(payload.get("relationship_to_holder")),
        "reporter_reason": _clean(payload.get("reporter_reason")),
        "witnesses_present": witnesses_present,
        "police_reported_date": _parse_date(payload.get("police_reported_date"), label="Date reported to police"),
        "charges_laid": _parse_bool(payload.get("charges_laid")),
        "charges_details": _clean(payload.get("charges_details")),
        "declaration_position": _clean(payload.get("declaration_position")),
    }
    if gst_registered is not True:
        claim_values["abn"] = None
        claim_values["gst_itc_percent"] = None
    if is_policyholder is True:
        claim_values["relationship_to_holder"] = None
        claim_values["reporter_reason"] = None
    if witnesses_present is not True:
        witnesses = []
    if police_involved is not True:
        claim_values["police_report_number"] = None
        claim_values["police_reported_date"] = None
        claim_values["charges_laid"] = None
        claim_values["charges_details"] = None
    if others_involved is not True:
        other_parties = []
        for key in (
            "other_party_name",
            "other_party_phone",
            "other_party_email",
            "other_party_address",
            "other_party_vehicle_reg",
            "other_party_insurer",
        ):
            claim_values[key] = None

    motor_values = _parse_motor(payload) if insurance_type == "motor" else None
    property_values = _parse_property(payload) if insurance_type == "property" else None
    contents = _parse_contents(payload) if insurance_type == "property" else []
    if property_values is not None:
        claim_values["property_damaged"] = property_values.get("building_damaged")
        claim_values["estimated_value"] = property_values.get("contents_total_value") or claim_values["estimated_value"]
        if property_values.get("contents_affected") is not True:
            contents = []
        if property_values.get("other_person_responsible") is not True and insurance_type == "property":
            other_parties = []
    if motor_values is not None and motor_values.get("vehicle_driven") is not True:
        for key in list(motor_values):
            if key.startswith("driver_") or key in {"policyholder_was_driver", "alcohol_or_drugs", "alcohol_details"}:
                motor_values[key] = None

    return {
        "claim": claim_values,
        "motor": motor_values,
        "property": property_values,
        "witnesses": witnesses,
        "other_parties": other_parties,
        "contents": contents,
    }


def validate_submit(policy_id: int | None, parsed: dict[str, Any]) -> None:
    values = parsed["claim"]
    _require(policy_id, "Policy")
    _require(values["insurance_type"], "Insurance type")
    _require(values["holder_first_name"] or values["claimant_name"], "First name")
    _require(values["holder_last_name"] or values["claimant_name"], "Last name")
    _require(values["claimant_email"], "Email address")
    _require(values["claimant_phone"], "Phone number")
    _require(values["incident_date"], "Date the incident occurred")
    _require(values["incident_description"], "What happened")
    if values["is_policyholder"] is None:
        raise ClaimSubmitError("Say whether you are the policy holder.")
    if not values["declaration_accepted"]:
        raise ClaimSubmitError("Confirm the declaration before submitting.")
    _require(values["declaration_name"], "Declaration name")
    if values["declaration_date"] is None:
        values["declaration_date"] = date.today()

    if values["insurance_type"] == "motor":
        _require(values["incident_street"] or values["incident_location"], "Where the incident occurred")
        motor = parsed.get("motor") or {}
        _require(motor.get("vehicle_registration"), "Vehicle registration number")
        _require(motor.get("vehicle_year"), "Vehicle year")
        _require(motor.get("vehicle_make"), "Vehicle make")
        if motor.get("vehicle_driven") is None:
            raise ClaimSubmitError("Say whether the insured vehicle was being driven.")
    elif values["insurance_type"] == "property":
        if values["claim_type"] not in PROPERTY_CLAIM_TYPE_VALUES:
            raise ClaimSubmitError("Choose what type of property claim you are making.")


async def save_form_children(db: AsyncSession, claim: Claim, parsed: dict[str, Any]) -> None:
    claim_id = claim.claim_id
    await db.flush()

    existing_motor = await db.get(MotorClaim, claim_id)
    existing_property = await db.get(PropertyClaim, claim_id)
    if parsed["motor"] is None and existing_motor is not None:
        await db.delete(existing_motor)
    if parsed["property"] is None and existing_property is not None:
        await db.delete(existing_property)

    if parsed["motor"] is not None:
        motor = existing_motor or MotorClaim(claim_id=claim_id)
        for field, value in parsed["motor"].items():
            setattr(motor, field, value)
        if existing_motor is None:
            db.add(motor)
    if parsed["property"] is not None:
        detail = existing_property or PropertyClaim(claim_id=claim_id)
        for field, value in parsed["property"].items():
            setattr(detail, field, value)
        if existing_property is None:
            db.add(detail)

    from sqlalchemy import delete

    await db.execute(delete(ClaimWitness).where(ClaimWitness.claim_id == claim_id))
    await db.execute(delete(ClaimOtherParty).where(ClaimOtherParty.claim_id == claim_id))
    await db.execute(delete(PropertyContentsItem).where(PropertyContentsItem.claim_id == claim_id))
    for index, witness in enumerate(parsed["witnesses"], start=1):
        db.add(ClaimWitness(claim_id=claim_id, sequence=index, **witness))
    for index, party in enumerate(parsed["other_parties"], start=1):
        db.add(ClaimOtherParty(claim_id=claim_id, sequence=index, **party))
    for item in parsed["contents"]:
        db.add(PropertyContentsItem(claim_id=claim_id, **item))


def payload_from_form(form: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in form.keys():
        if key in {"files", "intent", "policy_id", "claim_id"}:
            continue
        values = [
            str(item).strip()
            for item in form.getlist(key)
            if not hasattr(item, "filename") and str(item).strip()
        ]
        if not values:
            payload[key] = None
        elif len(values) == 1:
            payload[key] = values[0]
        else:
            payload[key] = values
    return payload


def posted_draft_from_payload(payload: dict[str, Any], policy_id: int | None, claim_id: int | None) -> dict[str, Any]:
    draft = dict(payload)
    draft["policy_id"] = policy_id
    draft["claim_id"] = claim_id
    for key, value in list(draft.items()):
        if isinstance(value, str) and value.lower() in {"yes", "true", "on", "1"}:
            draft[key] = True
        elif isinstance(value, str) and value.lower() in {"no", "false", "off", "0"}:
            draft[key] = False
    return draft


WITNESS_FIELDS = (
    "title",
    "first_name",
    "last_name",
    "unit",
    "street_number",
    "street_name",
    "suburb",
    "state",
    "postcode",
    "phone",
    "email",
)
OTHER_PARTY_FIELDS = WITNESS_FIELDS + (
    "company_name",
    "insurance_company",
    "insurance_policy_number",
    "insurance_claim_number",
    "licence_number",
    "vehicle_registration",
    "vehicle_year",
    "vehicle_make",
    "vehicle_model",
    "vehicle_type",
)


def _option_list(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in pairs]


def _plain_options(values: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"value": value, "label": value} for value in values]


def _create_child_table(cur: Any, table: str, columns: dict[str, str]) -> None:
    col_sql = ", ".join(f"{name} {ddl}" for name, ddl in columns.items())
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            claim_id INTEGER PRIMARY KEY REFERENCES claim(claim_id) ON DELETE CASCADE,
            {col_sql}
        )
        """
    )
    for name, ddl in columns.items():
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}")


def _fetch_one(cur: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([col[0] for col in cur.description], row))


def _fetch_all(cur: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return _clean(value[0] if value else None)
    text = sanitize_free_text(str(value)).strip()
    return text or None


def _parse_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"yes", "true", "1", "on"}:
        return True
    if lowered in {"no", "false", "0", "off"}:
        return False
    raise ClaimSubmitError("Use Yes or No for the yes/no questions.")


def _parse_date(value: Any, *, label: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ClaimSubmitError(f"{label} must be a valid date.")


def _parse_time(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ClaimSubmitError("Approximate time must be HH:MM.")


def _parse_money(value: Any) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ClaimSubmitError("Estimated value must be a number.") from exc
    if amount < 0:
        raise ClaimSubmitError("Estimated value cannot be negative.")
    return amount


def _parse_multi(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        parts = [_clean(item) for item in value]
    else:
        parts = [_clean(part) for part in str(value).split(",")]
    joined = ", ".join(part for part in parts if part)
    return joined or None


def _require(value: Any, label: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ClaimSubmitError(f"{label} is required.")


def _join_name(first: Any, last: Any) -> str | None:
    text = " ".join(part for part in (_clean(first), _clean(last)) if part)
    return text or None


def _join_address(*parts: Any) -> str | None:
    text = ", ".join(str(part).strip() for part in parts if part)
    return text or None


def _parse_people(
    payload: dict[str, Any],
    prefix: str,
    count: int,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    people: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        person: dict[str, Any] = {}
        filled = False
        for field in fields:
            raw = payload.get(f"{prefix}_{index}_{field}")
            if field == "vehicle_damage_areas":
                continue
            person[field] = _clean(raw)
            if person[field]:
                filled = True
        if prefix == "other":
            person["vehicle_damage_areas"] = _parse_multi(payload, f"{prefix}_{index}_vehicle_damage")
            if person["vehicle_damage_areas"]:
                filled = True
        if filled:
            people.append(person)
    return people


def _parse_motor(payload: dict[str, Any]) -> dict[str, Any]:
    vehicle_driven = _parse_bool(payload.get("vehicle_driven"))
    values = {
        "person_injured": _parse_bool(payload.get("person_injured")),
        "vehicle_driven": vehicle_driven,
        "policyholder_was_driver": _parse_bool(payload.get("policyholder_was_driver")),
        "driver_title": _clean(payload.get("driver_title")),
        "driver_first_name": _clean(payload.get("driver_first_name")),
        "driver_last_name": _clean(payload.get("driver_last_name")),
        "driver_dob": _parse_date(payload.get("driver_dob"), label="Driver date of birth"),
        "driver_phone": _clean(payload.get("driver_phone")),
        "driver_email": _clean(payload.get("driver_email")),
        "driver_licence_number": _clean(payload.get("driver_licence_number")),
        "driver_licence_years": _clean(payload.get("driver_licence_years")),
        "driver_unit": _clean(payload.get("driver_unit")),
        "driver_street_number": _clean(payload.get("driver_street_number")),
        "driver_street_name": _clean(payload.get("driver_street_name")),
        "driver_suburb": _clean(payload.get("driver_suburb")),
        "driver_state": _clean(payload.get("driver_state")),
        "driver_postcode": _clean(payload.get("driver_postcode")),
        "alcohol_or_drugs": _parse_bool(payload.get("alcohol_or_drugs")),
        "alcohol_details": _clean(payload.get("alcohol_details")),
        "vehicle_registration": _clean(payload.get("vehicle_registration")),
        "vehicle_year": _clean(payload.get("vehicle_year")),
        "vehicle_make": _clean(payload.get("vehicle_make")),
        "vehicle_model": _clean(payload.get("vehicle_model")),
        "vehicle_type": _clean(payload.get("vehicle_type")),
        "vehicle_damage_areas": _parse_multi(payload, "vehicle_damage"),
        "vehicle_towed": _parse_bool(payload.get("vehicle_towed")),
        "vehicle_now_location": _clean(payload.get("vehicle_now_location")),
        "airbags_deployed": _parse_bool(payload.get("airbags_deployed")),
        "speed_over_40": _parse_bool(payload.get("speed_over_40")),
        "other_vehicle_involved": _parse_bool(payload.get("other_vehicle_involved")),
        "other_property_damaged": _parse_bool(payload.get("other_property_damaged")),
        "licence_cancelled_3yrs": _parse_bool(payload.get("licence_cancelled_3yrs")),
        "cancelled_fine_defaults": _parse_bool(payload.get("cancelled_fine_defaults")),
        "convicted_alcohol_crime_3yrs": _parse_bool(payload.get("convicted_alcohol_crime_3yrs")),
        "insurance_declined_5yrs": _parse_bool(payload.get("insurance_declined_5yrs")),
    }
    if values["vehicle_towed"] is not True:
        values["vehicle_now_location"] = None
    if values["alcohol_or_drugs"] is not True:
        values["alcohol_details"] = None
    if values["licence_cancelled_3yrs"] is not True:
        values["cancelled_fine_defaults"] = None
    return values


def _parse_property(payload: dict[str, Any]) -> dict[str, Any]:
    contents_affected = _parse_bool(payload.get("contents_affected"))
    values = {
        "postal_same_as_insured": _parse_bool(payload.get("postal_same_as_insured")),
        "incident_at_insured_address": _parse_bool(payload.get("incident_at_insured_address")),
        "broker_name": _clean(payload.get("broker_name")),
        "broker_phone": _clean(payload.get("broker_phone")),
        "notify_policyholder": _parse_bool(payload.get("notify_policyholder")),
        "building_damaged": _parse_bool(payload.get("building_damaged")),
        "building_areas": _parse_multi(payload, "building_area"),
        "bathroom_rooms": _clean(payload.get("bathroom_rooms")),
        "bedroom_rooms": _clean(payload.get("bedroom_rooms")),
        "lounge_rooms": _clean(payload.get("lounge_rooms")),
        "damage_carpet": _clean(payload.get("damage_carpet")),
        "damage_ceiling": _clean(payload.get("damage_ceiling")),
        "damage_floor": _clean(payload.get("damage_floor")),
        "damage_wall": _clean(payload.get("damage_wall")),
        "damage_windows": _clean(payload.get("damage_windows")),
        "damage_other": _clean(payload.get("damage_other")),
        "property_secure": _parse_bool(payload.get("property_secure")),
        "repairs_done": _parse_bool(payload.get("repairs_done")),
        "property_habitable": _parse_bool(payload.get("property_habitable")),
        "contents_affected": contents_affected,
        "contents_total_value": _parse_money(payload.get("contents_total_value")),
        "other_person_responsible": _parse_bool(payload.get("other_person_responsible")),
        "convicted_crime_5yrs": _parse_bool(payload.get("convicted_crime_5yrs")),
        "insurance_declined_5yrs": _parse_bool(payload.get("insurance_declined_5yrs")),
    }
    if values["building_damaged"] is not True:
        values["building_areas"] = None
        values["bathroom_rooms"] = None
        values["bedroom_rooms"] = None
        values["lounge_rooms"] = None
        values["damage_carpet"] = None
        values["damage_ceiling"] = None
        values["damage_floor"] = None
        values["damage_wall"] = None
        values["damage_windows"] = None
        values["damage_other"] = None
        values["property_secure"] = None
        values["repairs_done"] = None
        values["property_habitable"] = None
    if contents_affected is not True:
        values["contents_total_value"] = None
    return values


def _parse_contents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for category, _label in CONTENTS_CATEGORIES:
        description = _clean(payload.get(f"contents_{category}_description"))
        value = _parse_money(payload.get(f"contents_{category}_value"))
        if description or value is not None:
            items.append({"category": category, "description": description, "estimated_value": value})
    return items
