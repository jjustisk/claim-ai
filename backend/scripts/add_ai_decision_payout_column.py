"""One-off migration: adds ai_decision.suggested_payout.

Run from backend/:
    python scripts/add_ai_decision_payout_column.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("ALTER TABLE ai_decision ADD COLUMN IF NOT EXISTS suggested_payout NUMERIC(12, 2)")

conn.commit()
print("Migration complete: ai_decision.suggested_payout ready.")
conn.close()
