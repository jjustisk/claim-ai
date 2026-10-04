"""Two motor draft claims for priya.nair@claim.ai (seeded PDS + schedule)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts.create_motor_drafts_demo import (  # noqa: E402
    API,
    CLAIMS,
    PASSWORD,
    base_motor_fields,
    motor_policy_id_for_customer,
)

EMAIL = "priya.nair@claim.ai"


def priya_fields(policy_id: int) -> dict[str, str]:
    data = base_motor_fields(policy_id)
    data.update(
        {
            "holder_title": "Ms",
            "holder_first_name": "Priya",
            "holder_last_name": "Nair",
            "holder_unit": "5",
            "holder_street_number": "22",
            "holder_street_name": "Ocean View Road",
            "holder_suburb": "Fremantle",
            "holder_state": "WA",
            "holder_postcode": "6160",
            "holder_email": EMAIL,
            "vehicle_registration": "1PNR001",
        }
    )
    return data


def main() -> None:
    policy_id = motor_policy_id_for_customer(EMAIL)
    print(f"Customer: {EMAIL}")
    print(f"Motor policy_id={policy_id} (SCMI-MV-TPFT-317642)")

    login = httpx.post(
        f"{API}/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
        timeout=30.0,
    )
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    regs = ["1PNR001", "1PNR002"]
    for idx, extra in enumerate(CLAIMS, start=1):
        data = priya_fields(policy_id)
        data.update(extra)
        data["vehicle_registration"] = regs[idx - 1]
        form = {k: v for k, v in data.items() if k != "vehicle_damage"}
        form["vehicle_damage"] = extra.get("vehicle_damage", "front bumper")

        resp = httpx.post(f"{API}/claims/", data=form, headers=headers, timeout=60.0)
        resp.raise_for_status()
        body = resp.json()
        print(
            f"Draft {idx}: claim_id={body['claim_id']} ref={body['claim_reference']} status={body['status']}"
        )

    print("\nLog in as", EMAIL, "password", PASSWORD)


if __name__ == "__main__":
    main()
