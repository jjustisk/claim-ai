"""
One-off migration: adds claim_damage_assessment.model_severity and
.percent_area_affected.

severity is now the deterministic bucket derived from percent_area_affected
(see damage_description_services._classify_severity_from_percent);
model_severity keeps the model's own direct judgement for comparison.

Run from backend/:
    python scripts/add_damage_assessment_severity_columns.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("ALTER TABLE claim_damage_assessment ADD COLUMN IF NOT EXISTS model_severity VARCHAR(20)")
cur.execute("ALTER TABLE claim_damage_assessment ADD COLUMN IF NOT EXISTS percent_area_affected FLOAT")

conn.commit()
print("Migration complete: model_severity and percent_area_affected ready.")
conn.close()
