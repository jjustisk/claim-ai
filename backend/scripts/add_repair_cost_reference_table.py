"""
One-off migration: adds the `repair_cost_reference` table.

Run from backend/:
    python scripts/add_repair_cost_reference_table.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS repair_cost_reference (
        reference_id SERIAL PRIMARY KEY,
        product VARCHAR(20) NOT NULL,
        damage_type VARCHAR(20),
        severity VARCHAR(20) NOT NULL,
        cost_low NUMERIC(12, 2) NOT NULL,
        cost_high NUMERIC(12, 2) NOT NULL,
        unit VARCHAR(30),
        region VARCHAR(10) DEFAULT 'AU',
        effective_date DATE
    )
    """
)
# Drops source from an earlier version of this table - not needed on the
# product; sourcing is mentioned separately (see seed_repair_cost_reference.py
# comments), not stored or surfaced in the app.
cur.execute("ALTER TABLE repair_cost_reference DROP COLUMN IF EXISTS source")
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_repair_cost_reference_lookup "
    "ON repair_cost_reference (product, damage_type, severity)"
)

conn.commit()
print("Migration complete: repair_cost_reference table ready.")
conn.close()
