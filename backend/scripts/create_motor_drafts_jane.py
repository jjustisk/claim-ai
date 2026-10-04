"""Create two motor draft claims for jane@example.com (presentation demo)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.connectors.db import get_sync_connection  # noqa: E402

API = "http://127.0.0.1:8000/api"
EMAIL = "jane@example.com"
PASSWORD = "ChangeMe123!"


def ensure_jane_motor_policy() -> int:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM customer WHERE email = %s", (EMAIL,))
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"Customer {EMAIL} not found — run auth seed first.")
            customer_id = row[0]

            cur.execute(
                """
                SELECT policy_id FROM policy
                WHERE customer_id = %s AND coverage_type ILIKE '%%Motor%%'
                ORDER BY policy_id LIMIT 1
                """,
                (customer_id,),
            )
            existing = cur.fetchone()
            if existing:
                return int(existing[0])

            cur.execute(
                """
                INSERT INTO policy (
                    customer_id, product_id, policy_number, coverage_type,
                    start_date, end_date, excess, max_payout, schedule_details
                )
                SELECT
                    %s, product_id, 'SCMI-MV-COMP-JANE-DEMO',
                    coverage_type, start_date, end_date, excess, max_payout, schedule_details
                FROM policy WHERE policy_id = 5
                RETURNING policy_id
                """,
                (customer_id,),
            )
            policy_id = int(cur.fetchone()[0])

            cur.execute(
                "SELECT 1 FROM pds_document WHERE policy_id = %s LIMIT 1",
                (policy_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO pds_document (policy_id, version, file_url, effective_date)
                    SELECT %s, version, file_url, effective_date
                    FROM pds_document WHERE policy_id = 5
                    """,
                    (policy_id,),
                )
        conn.commit()
        return policy_id
    finally:
        conn.close()


def base_motor_fields(policy_id: int) -> dict[str, str]:
    return {
        "intent": "draft",
        "policy_id": str(policy_id),
        "insurance_type": "motor",
        "holder_title": "Ms",
        "holder_first_name": "Jane",
        "holder_last_name": "Claimant",
        "holder_street_number": "42",
        "holder_street_name": "Harbour Street",
        "holder_suburb": "Sydney",
        "holder_state": "NSW",
        "holder_postcode": "2000",
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
        "vehicle_registration": "DEMO01",
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
        "vehicle_registration": "DEMO01",
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
        "vehicle_registration": "DEMO02",
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
    policy_id = ensure_jane_motor_policy()
    print(f"Motor policy for {EMAIL}: policy_id={policy_id}")

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
        if isinstance(data.get("vehicle_damage"), str):
            data["vehicle_damage"] = data["vehicle_damage"]  # single value ok in form list
        # multipart: repeat vehicle_damage if needed — httpx data with list
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

    print("\n--- Next steps ---")
    print(f"1. Log in to the Vue app as {EMAIL} / {PASSWORD}")
    print("2. Open My Claims, open each draft, add damage photos, tick declaration, Submit")
    print("Draft IDs:", [c["claim_id"] for c in created])
    print("References:", [c["claim_reference"] for c in created])


if __name__ == "__main__":
    main()
