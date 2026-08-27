"""
One-off migration: adds the `product` table and repoints PDS documents at
products instead of individual policies (PDS content is product-level, not
per-policy — see .claude/plans/stage0-pds-ingestion-retrieval.md).

- Creates `product` (product_id, product_name, insurance_type).
- Adds `policy.product_id`, `policy.excess`, `policy.max_payout`,
  `policy.schedule_details`.
- Adds `pds_document.product_id`; makes `pds_document.policy_id` nullable
  (schedule rows keep using policy_id, PDS rows move to product_id).
- Backfills product classification from `policy.coverage_type` using the
  same motor/property substring rule as
  claim_form.policy_matches_insurance_type.
- Dedupes existing per-policy PDS rows down to one row per product, deleting
  the redundant copies.

Run from backend/:
    python scripts/migrate_add_product_table.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

PRODUCTS = [
    ("Motor Vehicle Insurance", "motor"),
    ("Home Insurance", "property"),
]


def classify(coverage_type: str | None) -> str | None:
    text = (coverage_type or "").lower()
    if "motor" in text or "vehicle" in text:
        return "motor"
    if any(token in text for token in ("home", "building", "contents", "property")):
        return "property"
    return None


conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

# 1. product table.
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS product (
        product_id SERIAL PRIMARY KEY,
        product_name VARCHAR(100) NOT NULL UNIQUE,
        insurance_type VARCHAR(20)
    )
    """
)
product_ids: dict[str, int] = {}
for name, insurance_type in PRODUCTS:
    cur.execute(
        "SELECT product_id FROM product WHERE product_name = %s", (name,)
    )
    row = cur.fetchone()
    if row:
        product_ids[insurance_type] = row[0]
        continue
    cur.execute(
        "INSERT INTO product (product_name, insurance_type) VALUES (%s, %s) RETURNING product_id",
        (name, insurance_type),
    )
    product_ids[insurance_type] = cur.fetchone()[0]
print(f"Products: {product_ids}")

# 2. policy: new columns.
cur.execute("ALTER TABLE policy ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES product(product_id)")
cur.execute("ALTER TABLE policy ADD COLUMN IF NOT EXISTS excess NUMERIC(12, 2)")
cur.execute("ALTER TABLE policy ADD COLUMN IF NOT EXISTS max_payout NUMERIC(12, 2)")
cur.execute("ALTER TABLE policy ADD COLUMN IF NOT EXISTS schedule_details JSONB")

# 3. Backfill policy.product_id from coverage_type.
cur.execute("SELECT policy_id, coverage_type FROM policy WHERE product_id IS NULL")
rows = cur.fetchall()
unclassified: list[int] = []
for policy_id, coverage_type in rows:
    insurance_type = classify(coverage_type)
    if insurance_type is None:
        unclassified.append(policy_id)
        continue
    cur.execute(
        "UPDATE policy SET product_id = %s WHERE policy_id = %s",
        (product_ids[insurance_type], policy_id),
    )
print(f"Classified {len(rows) - len(unclassified)} of {len(rows)} policies.")
if unclassified:
    print(f"WARNING: could not classify coverage_type for policy_id(s): {unclassified} — left product_id NULL.")

# 4. pds_document: product_id column, policy_id becomes nullable.
cur.execute("ALTER TABLE pds_document ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES product(product_id)")
cur.execute("ALTER TABLE pds_document ALTER COLUMN policy_id DROP NOT NULL")

# 5. Dedupe: for each product, keep one canonical PDS row, delete the rest.
cur.execute(
    """
    SELECT d.pds_id, d.policy_id, p.product_id
    FROM pds_document d
    JOIN policy p ON p.policy_id = d.policy_id
    WHERE d.version = 'PDS' AND d.product_id IS NULL
    ORDER BY p.product_id, d.pds_id
    """
)
pds_rows = cur.fetchall()
seen_products: set[int] = set()
kept = 0
deleted = 0
for pds_id, policy_id, product_id in pds_rows:
    if product_id is None:
        continue
    if product_id in seen_products:
        cur.execute("DELETE FROM pds_document WHERE pds_id = %s", (pds_id,))
        deleted += 1
        continue
    seen_products.add(product_id)
    cur.execute(
        "UPDATE pds_document SET product_id = %s, policy_id = NULL WHERE pds_id = %s",
        (product_id, pds_id),
    )
    kept += 1
print(f"PDS documents: kept {kept} canonical row(s), deleted {deleted} duplicate(s).")

conn.commit()
print("Migration complete.")
conn.close()
