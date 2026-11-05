"""Add the demo accounts Noah Fischer and Daniel Reeves WITHOUT local policy PDFs.

The original customers (seed_policy_customers.py) already have their PDS and
policy-schedule files uploaded to Azure storage and recorded in the database.
This script links the two new Home Building policies to those existing files
instead of uploading anything, so backend/policy_docs is not needed.

Prerequisite: the original seed has been run once by someone on the team
(it creates the "Home Insurance" product and Amelia Hart's policy).

Run from backend/:
    python scripts/seed_demo_customers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seed_policy_customers as base  # noqa: E402  (same folder: reuses its helpers)
from app.connectors.db import get_sync_connection  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402
from app.services.claim_service import ensure_claim_form_columns, ensure_policy_customer_column  # noqa: E402

PRODUCT_NAME = "Home Insurance"
# Existing policy whose uploaded schedule file the demo policies point at.
SOURCE_POLICY_NUMBER = "SCHI-260901-1048"

ACCOUNTS = [
    {
        "name": "Noah Fischer",
        "email": "noah.fischer@claim.ai",
        "address": "27 Jarrah Street, Rockingham WA 6168",
        "policy_number": "SCHI-260901-4129",
        "coverage_type": "Home Insurance - Building",
    },
    {
        "name": "Daniel Reeves",
        "email": "daniel.reeves@claim.ai",
        "address": "6 Marri Close, Mandurah WA 6210",
        "policy_number": "SCHI-260901-5173",
        "coverage_type": "Home Insurance - Building",
    },
]


def _fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def _existing_product_and_pds(cur) -> tuple[int, str]:
    cur.execute("SELECT product_id FROM product WHERE product_name = %s", (PRODUCT_NAME,))
    row = cur.fetchone()
    if not row:
        _fail(f'Product "{PRODUCT_NAME}" not found. The original seed has not been run on this database.')
    product_id = int(row[0])
    cur.execute(
        "SELECT file_url FROM pds_document WHERE product_id = %s AND version = 'PDS'",
        (product_id,),
    )
    pds = cur.fetchone()
    if not pds:
        _fail(f'No PDS document recorded for "{PRODUCT_NAME}".')
    return product_id, str(pds[0])


def _existing_schedule_url(cur) -> str:
    cur.execute(
        """
        SELECT d.file_url
        FROM pds_document d
        JOIN policy p ON p.policy_id = d.policy_id
        WHERE p.policy_number = %s AND d.version = 'Policy Schedule'
        """,
        (SOURCE_POLICY_NUMBER,),
    )
    row = cur.fetchone()
    if not row:
        _fail(f"No policy schedule found for {SOURCE_POLICY_NUMBER}. The original seed has not been run.")
    return str(row[0])


def main() -> int:
    ensure_claim_form_columns()
    ensure_policy_customer_column()
    password_hash = hash_password(base.PASSWORD)
    conn = get_sync_connection()
    summary: list[str] = []
    try:
        with conn.cursor() as cur:
            product_id, pds_url = _existing_product_and_pds(cur)
            schedule_url = _existing_schedule_url(cur)
            for acct in ACCOUNTS:
                customer_id, customer_action = base.upsert_customer(
                    cur,
                    name=acct["name"],
                    email=acct["email"],
                    address=acct["address"],
                    password_hash=password_hash,
                )
                policy_id, policy_action = base.upsert_policy(
                    cur,
                    customer_id=customer_id,
                    product_id=product_id,
                    policy_number=acct["policy_number"],
                    coverage_type=acct["coverage_type"],
                )
                schedule_action = base.upsert_schedule_document(
                    cur, policy_id=policy_id, file_url=schedule_url
                )
                claim_id, reference, claim_action = base.upsert_draft_claim(
                    cur,
                    customer_id=customer_id,
                    policy_id=policy_id,
                    claimant_name=acct["name"],
                    claimant_email=acct["email"],
                )
                base.replace_claim_policy_docs(
                    cur,
                    claim_id=claim_id,
                    documents=[("PDS", pds_url), ("Policy Schedule", schedule_url)],
                )
                summary.append(
                    f"{acct['email']} id={customer_id} ({customer_action}); "
                    f"policy {acct['policy_number']} id={policy_id} ({policy_action}); "
                    f"schedule={schedule_action}; draft {reference} id={claim_id} ({claim_action})"
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("Demo seed complete.")
    for line in summary:
        print(" ", line)
    print()
    print(f"Login password for these accounts: {base.PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())