"""One-off migration: adds input_payload, output_payload, model_name to
audit_log.

Run from backend/:
    python scripts/add_audit_log_columns.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS input_payload JSONB")
cur.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS output_payload JSONB")
cur.execute("ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS model_name VARCHAR(50)")

conn.commit()
print("Migration complete: audit_log columns ready.")
conn.close()
