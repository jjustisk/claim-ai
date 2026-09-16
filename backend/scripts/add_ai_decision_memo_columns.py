"""One-off migration: adds ai_decision.assessor_memo and
ai_decision.customer_explanation.

Run from backend/:
    python scripts/add_ai_decision_memo_columns.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("ALTER TABLE ai_decision ADD COLUMN IF NOT EXISTS assessor_memo TEXT")
cur.execute("ALTER TABLE ai_decision ADD COLUMN IF NOT EXISTS customer_explanation TEXT")

conn.commit()
print("Migration complete: ai_decision.assessor_memo and customer_explanation ready.")
conn.close()
