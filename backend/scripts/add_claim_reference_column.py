"""
One-off migration: adds the `claim_reference` column to an existing `claim` table.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.claim_reference import generate_claim_reference
from app.database import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

# 1. Add the column as nullable first - existing rows can't satisfy a
#    NOT NULL constraint until they're backfilled below.
cur.execute("ALTER TABLE claim ADD COLUMN IF NOT EXISTS claim_reference VARCHAR(20)")

# 2. Backfill any pre-existing rows so NOT NULL can be applied safely.
cur.execute("SELECT claim_id FROM claim WHERE claim_reference IS NULL")
missing_ids = [row[0] for row in cur.fetchall()]
for claim_id in missing_ids:
    cur.execute(
        "UPDATE claim SET claim_reference = %s WHERE claim_id = %s",
        (generate_claim_reference(), claim_id),
    )
print(f"Backfilled {len(missing_ids)} existing row(s).")

# 3. Now that every row has a value, enforce NOT NULL + uniqueness.
cur.execute("ALTER TABLE claim ALTER COLUMN claim_reference SET NOT NULL")
cur.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_claim_claim_reference "
    "ON claim (claim_reference)"
)

conn.commit()
print("Migration complete: claim.claim_reference is live.")
conn.close()