"""Seed minimal local login accounts (no policy PDFs / Azure required).

Run inside the backend container or from backend/:
    python scripts/seed_local_auth_users.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.auth_service import hash_password
from app.connectors.db import get_sync_connection

PASSWORD = "ChangeMe123!"

USERS = [
    # (table, name, email, extra_cols)
    ("customer", "Demo Customer", "customer@email.com", {"phone": "0400000000", "address": "1 Demo St, Perth WA"}),
    ("assessor", "Demo Assessor", "assessor@insurance.com", {"role": "assessor"}),
]


def main() -> None:
    password_hash = hash_password(PASSWORD)
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            for table, name, email, extras in USERS:
                cur.execute(f"SELECT 1 FROM {table} WHERE email = %s", (email,))
                if cur.fetchone():
                    print(f"exists: {email} ({table})")
                    continue
                if table == "customer":
                    cur.execute(
                        """
                        INSERT INTO customer (name, email, hashed_password, phone, address)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (name, email, password_hash, extras.get("phone"), extras.get("address")),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO assessor (name, email, hashed_password, role)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (name, email, password_hash, extras.get("role")),
                    )
                print(f"created: {email} ({table})")
        conn.commit()
    finally:
        conn.close()

    print()
    print("Local login accounts (password for all):")
    print(f"  Customer: customer@email.com / {PASSWORD}")
    print(f"  Assessor: assessor@insurance.com / {PASSWORD}")


if __name__ == "__main__":
    main()
