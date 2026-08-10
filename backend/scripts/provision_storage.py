"""Create Azure Blob Storage containers for claim-ai.

Run from the backend directory:
    python scripts/provision_storage.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.storage import close_blob_service_client, ensure_container_exists


CONTAINERS = [
    ("images", settings.azure_storage_images_container_name),
    ("videos", settings.azure_storage_videos_container_name),
    ("pds-policies", settings.azure_storage_pds_policies_container_name),
]


async def main() -> None:
    if not settings.azure_storage_connection_string:
        print("ERROR: AZURE_STORAGE_CONNECTION_STRING is not set in .env")
        sys.exit(1)

    print(f"Storage account: claimaistorage")
    for label, container_name in CONTAINERS:
        container = await ensure_container_exists(container_name)
        exists = await container.exists()
        status = "ready" if exists else "failed"
        print(f"  [{status}] {label}: {container_name}")

    await close_blob_service_client()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
