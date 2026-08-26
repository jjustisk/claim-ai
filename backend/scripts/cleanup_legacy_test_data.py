"""Remove legacy manual test customers and orphan policies.

Run from backend/:
    python scripts/cleanup_legacy_test_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

LEGACY_EMAILS = ("claimant@test.com", "jane@example.com")
LEGACY_POLICY_NUMBERS = ("POL-TEST-001",)


def cleanup() -> None:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for email in LEGACY_EMAILS:
                cur.execute("SELECT customer_id FROM customer WHERE email = %s", (email,))
                row = cur.fetchone()
                if row is None:
                    continue
                customer_id = int(row[0])
                cur.execute(
                    "SELECT COUNT(*) FROM claim WHERE customer_id = %s AND status <> 'draft'",
                    (customer_id,),
                )
                if int(cur.fetchone()[0]) > 0:
                    print(f"Skip {email}: has submitted claims.")
                    continue
                cur.execute("DELETE FROM claim_document WHERE claim_id IN (SELECT claim_id FROM claim WHERE customer_id = %s)", (customer_id,))
                cur.execute("DELETE FROM notification WHERE customer_id = %s OR claim_id IN (SELECT claim_id FROM claim WHERE customer_id = %s)", (customer_id, customer_id))
                cur.execute("DELETE FROM claim WHERE customer_id = %s", (customer_id,))
                cur.execute("DELETE FROM customer WHERE customer_id = %s", (customer_id,))
                print(f"Removed legacy customer {email}.")

            for policy_number in LEGACY_POLICY_NUMBERS:
                cur.execute("SELECT policy_id FROM policy WHERE policy_number = %s", (policy_number,))
                row = cur.fetchone()
                if row is None:
                    continue
                policy_id = int(row[0])
                cur.execute("SELECT COUNT(*) FROM claim WHERE policy_id = %s", (policy_id,))
                if int(cur.fetchone()[0]) > 0:
                    print(f"Skip policy {policy_number}: still referenced by claims.")
                    continue
                cur.execute("DELETE FROM pds_document WHERE policy_id = %s", (policy_id,))
                cur.execute("DELETE FROM policy WHERE policy_id = %s", (policy_id,))
                print(f"Removed legacy policy {policy_number}.")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    cleanup()
    print("Cleanup complete.")
