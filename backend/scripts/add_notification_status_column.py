"""One-off migration: adds notification.status.

Run from backend/:
    python scripts/add_notification_status_column.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection

conn = get_sync_connection()
conn.autocommit = False
cur = conn.cursor()

cur.execute("ALTER TABLE notification ADD COLUMN IF NOT EXISTS status VARCHAR(20)")

conn.commit()
print("Migration complete: notification.status ready.")
conn.close()
