"""Replace claim image blobs that are not valid JPEG/PNG (e.g. encrypted PII raw bytes)."""

from __future__ import annotations

import asyncio
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.connectors.db import get_sync_connection  # noqa: E402
from app.connectors.storage import upload_image  # noqa: E402
from app.utils.image_bytes import is_valid_image_bytes  # noqa: E402
from app.connectors.storage import download_stored_blob  # noqa: E402


def make_demo_jpeg() -> bytes:
    img = Image.new("RGB", (800, 600), (90, 95, 100))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 280, 680, 520), fill=(50, 55, 60))
    draw.rectangle((200, 320, 420, 480), fill=(190, 60, 50))
    draw.text((210, 340), "Vehicle damage (demo)", fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def main() -> None:
    good = make_demo_jpeg()
    assert is_valid_image_bytes(good)

    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, claim_id, file_url, file_type
                FROM claim_document
                WHERE file_type IN ('image/jpeg', 'image/png')
                ORDER BY doc_id
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    fixed = 0
    for doc_id, claim_id, file_url, file_type in rows:
        if not file_url:
            continue
        try:
            data = await download_stored_blob(file_url)
        except Exception as exc:
            print(f"doc {doc_id}: download failed: {exc}")
            continue
        if is_valid_image_bytes(data):
            continue
        blob_name = file_url if not file_url.startswith("http") else file_url.split("/")[-1]
        await upload_image(blob_name, good, content_type="image/jpeg", overwrite=True)
        conn = get_sync_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE claim_document SET file_type = %s, sanitised_file_url = NULL WHERE doc_id = %s",
                    ("image/jpeg", doc_id),
                )
            conn.commit()
        finally:
            conn.close()
        fixed += 1
        print(f"Fixed doc_id={doc_id} claim_id={claim_id} blob={blob_name}")

    print(f"Done. Replaced {fixed} invalid image blob(s).")


if __name__ == "__main__":
    asyncio.run(main())
