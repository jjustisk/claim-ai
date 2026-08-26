"""Seed customers, policies, PDS/schedule blobs, and draft claims from policy_docs.

Run from backend/:
    python scripts/seed_policy_customers.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection
from app.connectors.storage import close_blob_service_client, upload_pds_policy
from app.services.auth_service import hash_password
from app.services.claim_service import ensure_claim_form_columns, generate_claim_reference

BACKEND_DIR = Path(__file__).resolve().parents[1]
POLICY_DOCS = BACKEND_DIR / "policy_docs"
PASSWORD = "ChangeMe123!"
PDF_TYPE = "application/pdf"
PERIOD_START = datetime(2026, 9, 1)
PERIOD_END = datetime(2027, 8, 31, 23, 59, 59)
EFFECTIVE = datetime(2026, 8, 26)

CUSTOMERS = [
    {
        "name": "Amelia Hart",
        "email": "amelia.hart@claim.ai",
        "address": "14 Banksia Avenue, Joondalup WA 6027",
        "policies": [
            {
                "policy_number": "SCHI-260901-1048",
                "coverage_type": "Home Insurance - Building",
                "pds_file": "Home_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Home_Policy_Schedule_01_Amelia_Hart_Building.pdf",
            },
            {
                "policy_number": "SCMI-MV-TP-104827",
                "coverage_type": "Motor Vehicle - Third Party Property Damage",
                "pds_file": "Motor_Vehicle_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Policy_Schedule_01_Amelia_Hart_Third_Party_Property_Damage.pdf",
            },
        ],
    },
    {
        "name": "Liam Bennett",
        "email": "liam.bennett@claim.ai",
        "address": "8 Wattle Crescent, Baldivis WA 6171",
        "policies": [
            {
                "policy_number": "SCHI-260901-2116",
                "coverage_type": "Home Insurance - Building & Contents",
                "pds_file": "Home_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Home_Policy_Schedule_02_Liam_Bennett_Building_Contents.pdf",
            },
            {
                "policy_number": "SCMI-MV-COMP-208315",
                "coverage_type": "Motor Vehicle - Comprehensive",
                "pds_file": "Motor_Vehicle_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Policy_Schedule_02_Liam_Bennett_Comprehensive.pdf",
            },
        ],
    },
    {
        "name": "Priya Nair",
        "email": "priya.nair@claim.ai",
        "address": "Unit 5, 22 Ocean View Road, Fremantle WA 6160",
        "policies": [
            {
                "policy_number": "SCHI-260901-3489",
                "coverage_type": "Home Insurance - Contents & Personal Valuables",
                "pds_file": "Home_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Home_Policy_Schedule_03_Priya_Nair_Contents_Valuables.pdf",
            },
            {
                "policy_number": "SCMI-MV-TPFT-317642",
                "coverage_type": "Motor Vehicle - Third Party Fire & Theft",
                "pds_file": "Motor_Vehicle_Insurance_PDS_Full_Sample.pdf",
                "schedule_file": "Policy_Schedule_03_Priya_Nair_Third_Party_Fire_Theft.pdf",
            },
        ],
    },
]


def _read_pdf(filename: str) -> bytes:
    path = POLICY_DOCS / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing policy document: {path}")
    return path.read_bytes()


def _blob_name(email: str, policy_number: str, kind: str) -> str:
    filename = "pds.pdf" if kind == "PDS" else "policy-schedule.pdf"
    return f"customers/{email}/{policy_number}/{filename}"


def upsert_customer(cur, *, name: str, email: str, address: str, password_hash: str) -> tuple[int, str]:
    cur.execute("SELECT customer_id FROM customer WHERE email = %s", (email,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE customer
            SET name = %s, hashed_password = %s, address = %s
            WHERE customer_id = %s
            """,
            (name, password_hash, address, row[0]),
        )
        return int(row[0]), "updated"
    cur.execute(
        """
        INSERT INTO customer (name, email, hashed_password, address)
        VALUES (%s, %s, %s, %s)
        RETURNING customer_id
        """,
        (name, email, password_hash, address),
    )
    return int(cur.fetchone()[0]), "created"


def upsert_policy(cur, *, policy_number: str, coverage_type: str) -> tuple[int, str]:
    cur.execute("SELECT policy_id FROM policy WHERE policy_number = %s", (policy_number,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE policy
            SET coverage_type = %s, start_date = %s, end_date = %s
            WHERE policy_id = %s
            """,
            (coverage_type, PERIOD_START, PERIOD_END, row[0]),
        )
        return int(row[0]), "updated"
    cur.execute(
        """
        INSERT INTO policy (policy_number, coverage_type, start_date, end_date)
        VALUES (%s, %s, %s, %s)
        RETURNING policy_id
        """,
        (policy_number, coverage_type, PERIOD_START, PERIOD_END),
    )
    return int(cur.fetchone()[0]), "created"


def upsert_pds_document(cur, *, policy_id: int, version: str, file_url: str) -> str:
    cur.execute(
        """
        SELECT pds_id FROM pds_document
        WHERE policy_id = %s AND version = %s
        """,
        (policy_id, version),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE pds_document
            SET file_url = %s, effective_date = %s
            WHERE pds_id = %s
            """,
            (file_url, EFFECTIVE, row[0]),
        )
        return "updated"
    cur.execute(
        """
        INSERT INTO pds_document (policy_id, version, file_url, effective_date)
        VALUES (%s, %s, %s, %s)
        """,
        (policy_id, version, file_url, EFFECTIVE),
    )
    return "created"


def upsert_draft_claim(
    cur,
    *,
    customer_id: int,
    policy_id: int,
    claimant_name: str,
    claimant_email: str,
) -> tuple[int, str, str]:
    cur.execute(
        """
        SELECT claim_id, claim_reference
        FROM claim
        WHERE customer_id = %s AND policy_id = %s AND status = 'draft'
        ORDER BY claim_id
        LIMIT 1
        """,
        (customer_id, policy_id),
    )
    row = cur.fetchone()
    if row:
        claim_id, reference = int(row[0]), str(row[1])
        cur.execute(
            """
            UPDATE claim
            SET claimant_name = %s,
                claimant_email = %s,
                status = 'draft'
            WHERE claim_id = %s
            """,
            (claimant_name, claimant_email, claim_id),
        )
        return claim_id, reference, "updated"
    reference = generate_claim_reference()
    cur.execute(
        """
        INSERT INTO claim (
            claim_reference, customer_id, policy_id, status,
            claimant_name, claimant_email, submission_date
        )
        VALUES (%s, %s, %s, 'draft', %s, %s, %s)
        RETURNING claim_id
        """,
        (
            reference,
            customer_id,
            policy_id,
            claimant_name,
            claimant_email,
            datetime.now(timezone.utc),
        ),
    )
    return int(cur.fetchone()[0]), reference, "created"


def replace_claim_policy_docs(cur, *, claim_id: int, documents: list[tuple[str, str]]) -> None:
    for _kind, file_url in documents:
        blob_name = file_url.rstrip("/").split("/")[-1]
        cur.execute(
            """
            DELETE FROM claim_document
            WHERE claim_id = %s AND file_url LIKE %s
            """,
            (claim_id, f"%/{blob_name}"),
        )
        cur.execute(
            """
            INSERT INTO claim_document (claim_id, file_type, file_url, upload_date)
            VALUES (%s, %s, %s, %s)
            """,
            (claim_id, PDF_TYPE, file_url, datetime.now(timezone.utc)),
        )


async def upload_policy_docs(email: str, policy_number: str, pds_file: str, schedule_file: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    for kind, filename in (("PDS", pds_file), ("Policy Schedule", schedule_file)):
        blob_name = _blob_name(email, policy_number, kind)
        urls[kind] = await upload_pds_policy(
            blob_name,
            _read_pdf(filename),
            content_type=PDF_TYPE,
            overwrite=True,
        )
    return urls


async def seed() -> None:
    if not POLICY_DOCS.is_dir():
        raise FileNotFoundError(f"policy_docs not found: {POLICY_DOCS}")

    ensure_claim_form_columns()
    password_hash = hash_password(PASSWORD)
    conn = get_sync_connection()
    summary: list[str] = []
    try:
        with conn.cursor() as cur:
            for customer in CUSTOMERS:
                customer_id, customer_action = upsert_customer(
                    cur,
                    name=customer["name"],
                    email=customer["email"],
                    address=customer["address"],
                    password_hash=password_hash,
                )
                summary.append(
                    f"customer {customer['email']} id={customer_id} ({customer_action})"
                )
                for policy in customer["policies"]:
                    policy_id, policy_action = upsert_policy(
                        cur,
                        policy_number=policy["policy_number"],
                        coverage_type=policy["coverage_type"],
                    )
                    urls = await upload_policy_docs(
                        customer["email"],
                        policy["policy_number"],
                        policy["pds_file"],
                        policy["schedule_file"],
                    )
                    pds_action = upsert_pds_document(
                        cur,
                        policy_id=policy_id,
                        version="PDS",
                        file_url=urls["PDS"],
                    )
                    schedule_action = upsert_pds_document(
                        cur,
                        policy_id=policy_id,
                        version="Policy Schedule",
                        file_url=urls["Policy Schedule"],
                    )
                    claim_id, reference, claim_action = upsert_draft_claim(
                        cur,
                        customer_id=customer_id,
                        policy_id=policy_id,
                        claimant_name=customer["name"],
                        claimant_email=customer["email"],
                    )
                    replace_claim_policy_docs(
                        cur,
                        claim_id=claim_id,
                        documents=list(urls.items()),
                    )
                    summary.append(
                        f"  policy {policy['policy_number']} id={policy_id} ({policy_action}); "
                        f"pds={pds_action}; schedule={schedule_action}; "
                        f"draft {reference} id={claim_id} ({claim_action})"
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        await close_blob_service_client()

    print("Seed complete.")
    for line in summary:
        print(line)
    print()
    print(f"Login password for all seeded customers: {PASSWORD}")


def main() -> int:
    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
