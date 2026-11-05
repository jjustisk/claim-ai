"""Delete a demo customer's SUBMITTED claims so the demo can be run again.

Keeps the customer account, their policies and their draft claims. Removes, for
each non-draft claim of that customer: audit log, notifications, AI decisions,
damage assessments, reviews, claim documents (including image hashes) and the
claim itself (form detail tables are removed by ON DELETE CASCADE).

Dry run by default - it only prints what it WOULD delete:
    python scripts/reset_demo_claims.py noah.fischer@claim.ai
Actually delete:
    python scripts/reset_demo_claims.py noah.fischer@claim.ai --yes

Note: photo files already uploaded to Azure storage are left in place (orphaned).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection  # noqa: E402

# (label, delete SQL). %(ids)s is a list of claim ids; order matters (children first).
STEPS = [
    ("audit_log", "DELETE FROM audit_log WHERE decision_id IN (SELECT decision_id FROM ai_decision WHERE claim_id = ANY(%(ids)s))"),
    ("notification", "DELETE FROM notification WHERE claim_id = ANY(%(ids)s)"),
    ("ai_decision", "DELETE FROM ai_decision WHERE claim_id = ANY(%(ids)s)"),
    ("claim_damage_assessment", "DELETE FROM claim_damage_assessment WHERE claim_id = ANY(%(ids)s)"),
    ("reviews", "DELETE FROM reviews WHERE claim_id = ANY(%(ids)s)"),
    ("claim_document", "DELETE FROM claim_document WHERE claim_id = ANY(%(ids)s)"),
    ("claim", "DELETE FROM claim WHERE claim_id = ANY(%(ids)s)"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", help="customer email, e.g. noah.fischer@claim.ai")
    parser.add_argument("--yes", action="store_true", help="really delete (default is a dry run)")
    args = parser.parse_args()

    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id, name FROM customer WHERE email = %s", (args.email,))
            row = cur.fetchone()
            if not row:
                print(f"No customer with email {args.email}")
                return 1
            customer_id, name = int(row[0]), row[1]

            cur.execute(
                "SELECT claim_id, claim_reference, status FROM claim "
                "WHERE customer_id = %s AND status <> 'draft' ORDER BY claim_id",
                (customer_id,),
            )
            claims = cur.fetchall()
            print(f"Customer: {name} <{args.email}> (id={customer_id})")
            if not claims:
                print("No submitted claims to delete. Drafts are never touched.")
                return 0
            for claim_id, reference, status in claims:
                print(f"  claim {claim_id} {reference} [{status}]")
            ids = [int(c[0]) for c in claims]

            for label, sql in STEPS:
                if args.yes:
                    cur.execute(sql, {"ids": ids})
                    print(f"  deleted {cur.rowcount:>3} from {label}")
                else:
                    count_sql = sql.replace("DELETE FROM", "SELECT count(*) FROM", 1)
                    cur.execute(count_sql, {"ids": ids})
                    print(f"  would delete {cur.fetchone()[0]:>3} from {label}")
        if args.yes:
            conn.commit()
            print("Done. The customer account, policies and drafts are untouched.")
        else:
            conn.rollback()
            print("Dry run only - nothing changed. Add --yes to delete.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())