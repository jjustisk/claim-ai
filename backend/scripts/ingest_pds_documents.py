"""Runs Stage 0 ingestion against everything already seeded:

1. For each product's PDS document: download from blob, chunk, embed, and
   upsert into the ChromaDB `pds_clauses` collection.
2. For each policy's Policy Schedule document: download from blob, parse
   structured fields, and write them onto the `policy` row (excess,
   max_payout, schedule_details).

Safe to re-run — PDS chunks are upserted by deterministic id (existing
chunks for a pds_id are cleared first), and schedule fields are simply
overwritten.

Run from backend/:
    python scripts/ingest_pds_documents.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.db import get_sync_connection
from app.connectors.storage import close_blob_service_client, download_stored_blob
from app.services.pds_ingestion_service import ingest_product_pds
from app.services.policy_schedule_ingestion_service import extract_schedule_fields


def _fetch_pds_documents(cur) -> list[tuple[int, int, str]]:
    cur.execute(
        """
        SELECT pds_id, product_id, file_url
        FROM pds_document
        WHERE version = 'PDS' AND product_id IS NOT NULL
        ORDER BY pds_id
        """
    )
    return [(int(pds_id), int(product_id), file_url) for pds_id, product_id, file_url in cur.fetchall()]


def _fetch_schedule_documents(cur) -> list[tuple[int, int, str]]:
    cur.execute(
        """
        SELECT d.pds_id, d.policy_id, d.file_url
        FROM pds_document d
        WHERE d.version = 'Policy Schedule' AND d.policy_id IS NOT NULL
        ORDER BY d.pds_id
        """
    )
    return [(int(pds_id), int(policy_id), file_url) for pds_id, policy_id, file_url in cur.fetchall()]


async def ingest_pds(cur) -> None:
    for pds_id, product_id, file_url in _fetch_pds_documents(cur):
        pdf_bytes = await download_stored_blob(file_url)
        count = ingest_product_pds(
            pds_id=pds_id, product_id=product_id, version="PDS", pdf_bytes=pdf_bytes
        )
        print(f"PDS pds_id={pds_id} product_id={product_id}: {count} chunk(s) upserted.")


async def ingest_schedules(cur, conn) -> None:
    for pds_id, policy_id, file_url in _fetch_schedule_documents(cur):
        pdf_bytes = await download_stored_blob(file_url)
        fields = extract_schedule_fields(pdf_bytes)
        cur.execute(
            """
            UPDATE policy
            SET excess = %s, max_payout = %s, schedule_details = %s
            WHERE policy_id = %s
            """,
            (
                fields["excess"],
                fields["max_payout"],
                Jsonb(fields["schedule_details"]),
                policy_id,
            ),
        )
        conn.commit()
        print(
            f"Schedule pds_id={pds_id} policy_id={policy_id}: "
            f"excess={fields['excess']} max_payout={fields['max_payout']}"
        )


async def main() -> int:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            await ingest_pds(cur)
            await ingest_schedules(cur, conn)
    finally:
        conn.close()
        await close_blob_service_client()
    print("Ingestion complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
