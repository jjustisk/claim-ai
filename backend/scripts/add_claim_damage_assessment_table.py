"""
One-off migration: adds the `claim_damage_assessment` table.

Holds the Call 1 (Damage Description) output — a visual damage
classification produced from claim images alone: images_assessable,
damage_description, reasoning, damage_type, severity, image counts, plus
the model used and a timestamp. Kept separate from `ai_decision`, which
records the final coverage decision rather than this intermediate step.

Run from backend/:
    python scripts/add_claim_damage_assessment_table.py
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
    CREATE TABLE IF NOT EXISTS claim_damage_assessment (
        assessment_id SERIAL PRIMARY KEY,
        claim_id INTEGER NOT NULL REFERENCES claim(claim_id),
        images_assessable BOOLEAN NOT NULL,
        damage_description TEXT NOT NULL,
        reasoning TEXT NOT NULL,
        damage_type VARCHAR(20) NOT NULL,
        severity VARCHAR(20) NOT NULL,
        images_available INTEGER NOT NULL,
        images_assessed INTEGER NOT NULL,
        model VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
    )
    """
)
cur.execute(
    "CREATE INDEX IF NOT EXISTS ix_claim_damage_assessment_claim_id "
    "ON claim_damage_assessment (claim_id)"
)

conn.commit()
print("Migration complete: claim_damage_assessment table ready.")
conn.close()
