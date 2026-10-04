"""Create two motor draft claims for a seeded @claim.ai customer (full PDS + schedule)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.connectors.db import get_sync_connection  # noqa: E402

API = "http://127.0.0.1:8000/api"
EMAIL = "liam.bennett@claim.ai"
PASSWORD = "ChangeMe123!"


def motor_policy_id_for_customer(email: str) -> int:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.policy_id
                FROM policy p
                JOIN customer c ON c.customer_id = p.customer_id
                WHERE c.email = %s AND p.coverage_type ILIKE '%%Motor%%'
                ORDER BY p.policy_id
                LIMIT 1
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(
                    f"No motor policy for {email}. Run: python scripts/seed_policy_customers.py"
                )
            return int(row[0])
    finally:
        conn.close()


def base_motor_fields(policy_id: int) -> dict[str, str]:
    return {
        "intent": "draft",
        "policy_id": str(policy_id),
        "insurance_type": "motor",
        "holder_title": "Mr",
        "holder_first_name": "Liam",
        "holder_last_name": "Bennett",
        "holder_street_number": "8",
        "holder_street_name": "Wattle Crescent",
        "holder_suburb": "Baldivis",
        "holder_state": "WA",
        "holder_postcode": "6171",
        "holder_email": EMAIL,
        "holder_phone": "0412345678",
        "preferred_contact_method": "email",
        "is_policyholder": "yes",
        "incident_date": "2026-09-28",
        "incident_time": "08:15",
        "incident_street": "Parramatta Road",
        "incident_suburb": "Leichhardt",
        "incident_state": "NSW",
        "incident_postcode": "2040",
        "witnesses_present": "no",
        "police_involved": "no",
        "person_injured": "no",
        "vehicle_driven": "yes",
        "policyholder_was_driver": "yes",
        "alcohol_or_drugs": "no",
        "vehicle_registration": "1LMB001",
        "vehicle_type": "Sedan",
        "vehicle_year": "2020",
        "vehicle_make": "Toyota",
        "vehicle_model": "Corolla",
        "vehicle_towed": "no",
        "airbags_deployed": "no",
        "speed_over_40": "yes",
        "other_vehicle_involved": "no",
        "other_property_damaged": "no",
        "licence_cancelled_3yrs": "no",
        "convicted_alcohol_crime_3yrs": "no",
        "insurance_declined_5yrs": "no",
        "gst_registered": "no",
        "estimated_value": "4500",
    }


CLAIMS = [
    {
        "incident_description": (
            "I was driving in moderate morning traffic on Parramatta Road when the vehicle "
            "in front braked suddenly for a pedestrian crossing. I braked but could not stop "
            "in time and collided with the rear of the other car. My front bumper, bonnet, "
            "and radiator grille are damaged and the vehicle is still drivable."
        ),
        "loss_description": "Front-end collision damage to bumper, bonnet, and headlight area.",
        "vehicle_registration": "1LMB001",
        "vehicle_damage": "front bumper",
        "additional_comments": "Other driver acknowledged sudden stop; exchange details taken.",
    },
    {
        "incident_description": (
            "While reversing out of a supermarket car park bay, I misjudged the distance to "
            "a concrete pillar on my left. I scraped the driver side rear quarter panel and "
            "rear door against the pillar. No other vehicles were involved and there were no injuries."
        ),
        "loss_description": "Scrape and dent damage to driver side rear door and quarter panel.",
        "vehicle_registration": "1LMB002",
        "vehicle_year": "2019",
        "vehicle_make": "Mazda",
        "vehicle_model": "3",
        "vehicle_damage": "rear door",
        "additional_comments": "Damage is cosmetic; car is safe to drive.",
        "incident_date": "2026-09-25",
        "incident_time": "17:40",
        "incident_street": "Victoria Avenue",
        "incident_suburb": "Chatswood",
        "incident_state": "NSW",
        "incident_postcode": "2067",
        "speed_over_40": "no",
        "other_vehicle_involved": "no",
    },
]


def main() -> None:
    policy_id = motor_policy_id_for_customer(EMAIL)
    print(f"Customer: {EMAIL}")
    print(f"Motor policy_id={policy_id} (SCMI-MV-COMP-208315) with PDS + Policy Schedule on file")

    login = httpx.post(
        f"{API}/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
        timeout=30.0,
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created: list[dict] = []
    for idx, extra in enumerate(CLAIMS, start=1):
        data = base_motor_fields(policy_id)
        data.update(extra)
        form = {k: v for k, v in data.items() if k != "vehicle_damage"}
        form["vehicle_damage"] = extra.get("vehicle_damage", "front bumper")

        resp = httpx.post(f"{API}/claims/", data=form, headers=headers, timeout=60.0)
        if resp.status_code >= 400:
            print(f"Claim {idx} failed:", resp.status_code, resp.text)
            resp.raise_for_status()
        body = resp.json()
        created.append(body)
        print(
            f"Draft {idx}: claim_id={body['claim_id']} ref={body['claim_reference']} status={body['status']}"
        )

    print("\nLog in as", EMAIL, "password", PASSWORD)
    print("Draft claim_ids:", [c["claim_id"] for c in created])
    print("References:", [c["claim_reference"] for c in created])


if __name__ == "__main__":
    main()
