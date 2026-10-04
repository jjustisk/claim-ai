"""Create five fully prefilled motor DRAFT claims for priya.nair@claim.ai (no images)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from scripts.create_motor_drafts_demo import (  # noqa: E402
    API,
    PASSWORD,
    base_motor_fields,
    motor_policy_id_for_customer,
)
from scripts.create_motor_drafts_priya import EMAIL, priya_fields  # noqa: E402

TODAY = date.today().isoformat()

# Five distinct motor scenarios — all form fields filled; no photo upload.
DRAFTS: list[dict[str, str]] = [
    {
        "incident_date": "2026-09-30",
        "incident_time": "07:45",
        "incident_street": "Canning Highway",
        "incident_cross_street": "Stock Road",
        "incident_suburb": "Palmyra",
        "incident_state": "WA",
        "incident_postcode": "6157",
        "incident_description": (
            "I was travelling east on Canning Highway in light traffic when the car ahead "
            "stopped suddenly for a turning vehicle. I braked hard but clipped their rear "
            "bumper. My front bumper and number-plate panel are cracked; the car is still "
            "drivable. No one was injured."
        ),
        "loss_description": "Front bumper and number-plate panel cracked after rear-end impact.",
        "vehicle_registration": "1PNR101",
        "vehicle_type": "Sedan",
        "vehicle_year": "2021",
        "vehicle_make": "Toyota",
        "vehicle_model": "Corolla",
        "vehicle_damage": "front bumper",
        "speed_over_40": "yes",
        "other_vehicle_involved": "yes",
        "estimated_value": "3200",
        "additional_comments": "Exchanged details with the other driver; dashcam clip available if needed.",
    },
    {
        "incident_date": "2026-09-27",
        "incident_time": "18:20",
        "incident_street": "South Terrace",
        "incident_cross_street": "Collie Street",
        "incident_suburb": "Fremantle",
        "incident_state": "WA",
        "incident_postcode": "6160",
        "incident_description": (
            "While parking parallel on South Terrace, another vehicle scraped along my "
            "passenger side as they tried to squeeze past. Paint is scuffed along the front "
            "and rear passenger doors and the wing mirror glass is cracked."
        ),
        "loss_description": "Passenger-side door scrape and cracked wing-mirror glass.",
        "vehicle_registration": "1PNR102",
        "vehicle_type": "Hatchback",
        "vehicle_year": "2019",
        "vehicle_make": "Mazda",
        "vehicle_model": "3",
        "vehicle_damage": "side panel",
        "speed_over_40": "no",
        "other_vehicle_involved": "yes",
        "estimated_value": "2100",
        "additional_comments": "Other driver left a note with insurer details on my windscreen.",
    },
    {
        "incident_date": "2026-09-22",
        "incident_time": "12:10",
        "incident_street": "Booragoon Shopping Centre car park",
        "incident_suburb": "Booragoon",
        "incident_state": "WA",
        "incident_postcode": "6154",
        "incident_description": (
            "I reversed carefully out of a bay at Booragoon and misjudged clearance to a "
            "concrete bollard on the driver side. The rear door and quarter panel have a "
            "long scrape and a small dent. No other vehicles or people were involved."
        ),
        "loss_description": "Driver-side rear door scrape and quarter-panel dent from a bollard.",
        "vehicle_registration": "1PNR103",
        "vehicle_type": "SUV",
        "vehicle_year": "2022",
        "vehicle_make": "Hyundai",
        "vehicle_model": "Tucson",
        "vehicle_damage": "rear door",
        "speed_over_40": "no",
        "other_vehicle_involved": "no",
        "estimated_value": "1800",
        "additional_comments": "Centre security confirmed the bollard location on CCTV.",
    },
    {
        "incident_date": "2026-09-18",
        "incident_time": "21:05",
        "incident_street": "High Street",
        "incident_cross_street": "Ord Street",
        "incident_suburb": "Fremantle",
        "incident_state": "WA",
        "incident_postcode": "6160",
        "incident_description": (
            "Overnight my car was parked securely on High Street. In the morning I found "
            "the rear windscreen smashed and glass inside the cabin. Nothing appears to have "
            "been stolen from the glovebox or boot. Police attended and took a report."
        ),
        "loss_description": "Rear windscreen smashed while vehicle was parked overnight.",
        "vehicle_registration": "1PNR104",
        "vehicle_type": "Sedan",
        "vehicle_year": "2020",
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "vehicle_damage": "windscreen",
        "speed_over_40": "no",
        "other_vehicle_involved": "no",
        "police_involved": "yes",
        "police_report_number": "WA-2026-88421",
        "police_reported_date": "2026-09-19",
        "charges_laid": "no",
        "estimated_value": "950",
        "additional_comments": "Glass temporary-taped; arranging replacement this week.",
    },
    {
        "incident_date": "2026-09-12",
        "incident_time": "16:35",
        "incident_street": "Stirling Highway",
        "incident_cross_street": "Queen Victoria Street",
        "incident_suburb": "North Fremantle",
        "incident_state": "WA",
        "incident_postcode": "6159",
        "incident_description": (
            "A delivery van changed lanes into me without indicating on Stirling Highway. "
            "Contact was side-to-side. My front left guard is pushed in and the headlight "
            "lens is cracked. Both vehicles pulled over and exchanged details; no injuries."
        ),
        "loss_description": "Front left guard dented and headlight lens cracked after side swipe.",
        "vehicle_registration": "1PNR105",
        "vehicle_type": "Sedan",
        "vehicle_year": "2018",
        "vehicle_make": "Subaru",
        "vehicle_model": "Impreza",
        "vehicle_damage": "front guard",
        "speed_over_40": "yes",
        "other_vehicle_involved": "yes",
        "estimated_value": "4100",
        "additional_comments": "Other vehicle was a white Toyota HiAce; photos of their plate taken.",
    },
]


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

    created: list[dict] = []
    for idx, extra in enumerate(DRAFTS, start=1):
        data = priya_fields(policy_id)
        # Ensure contact / declaration are ready so only a photo is missing to submit.
        data.update(
            {
                "holder_phone": "0412 555 317",
                "preferred_contact_method": "email",
                "postal_same_as_insured": "yes",
                "declaration_accepted": "yes",
                "declaration_name": "Priya Nair",
                "declaration_date": TODAY,
                "loss_description": "",
            }
        )
        data.update(extra)
        form = {k: v for k, v in data.items() if k != "vehicle_damage"}
        form["vehicle_damage"] = extra.get("vehicle_damage", "front bumper")

        resp = httpx.post(f"{API}/claims/", data=form, headers=headers, timeout=60.0)
        if resp.status_code >= 400:
            print(f"Draft {idx} failed:", resp.status_code, resp.text)
            resp.raise_for_status()
        body = resp.json()
        created.append(body)
        print(
            f"Draft {idx}: claim_id={body['claim_id']} ref={body['claim_reference']} "
            f"status={body['status']} reg={form['vehicle_registration']}"
        )

    print("\nLog in as", EMAIL, "/", PASSWORD)
    print("No images attached — open each draft, add a photo, then submit.")
    print("Draft claim_ids:", [c["claim_id"] for c in created])


if __name__ == "__main__":
    main()
