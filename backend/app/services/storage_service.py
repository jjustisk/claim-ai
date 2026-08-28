"""Blob-storage helpers for the storage test UI.

Knows the images, videos, and PDS-policy containers: which file types
are allowed, how to list blobs, and how to upload a test file.
The storage page only renders the form; this file does the work.
"""

from __future__ import annotations

import json
import mimetypes
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from urllib.parse import quote

from app.config import settings
from app.connectors.storage import (
    download_blob,
    list_images,
    list_pds_policies,
    list_videos,
    upload_image,
    upload_pds_policy,
    upload_video,
)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"}
PDF_TYPES = {"application/pdf"}


@dataclass(frozen=True)
class ContainerConfig:
    key: str
    label: str
    container_name: str
    allowed_types: frozenset[str]
    accept: str
    drop_label: str
    hint: str
    empty_label: str
    list_fn: Callable[[], Awaitable[list[str]]]
    upload_fn: Callable[..., Awaitable[str]]


CONTAINERS: dict[str, ContainerConfig] = {
    "images": ContainerConfig(
        key="images",
        label="Images",
        container_name=settings.azure_storage_images_container_name,
        allowed_types=frozenset(IMAGE_TYPES),
        accept="image/*",
        drop_label="Drag & drop an image here",
        hint="JPEG, PNG, GIF, WebP, BMP",
        empty_label="No images yet.",
        list_fn=list_images,
        upload_fn=upload_image,
    ),
    "videos": ContainerConfig(
        key="videos",
        label="Videos",
        container_name=settings.azure_storage_videos_container_name,
        allowed_types=frozenset(VIDEO_TYPES),
        accept="video/*",
        drop_label="Drag & drop a video here",
        hint="MP4, WebM, MOV, AVI",
        empty_label="No videos yet.",
        list_fn=list_videos,
        upload_fn=upload_video,
    ),
    "pds-policies": ContainerConfig(
        key="pds-policies",
        label="PDS Policies",
        container_name=settings.azure_storage_pds_policies_container_name,
        allowed_types=frozenset(PDF_TYPES),
        accept="application/pdf,.pdf",
        drop_label="Drag & drop a policy PDF here",
        hint="PDF only",
        empty_label="No policy PDFs yet.",
        list_fn=list_pds_policies,
        upload_fn=upload_pds_policy,
    ),
}


def connection_string_configured() -> bool:
    return bool(settings.azure_storage_connection_string)


def get_container(key: str) -> ContainerConfig | None:
    return CONTAINERS.get(key)


def containers_public_json() -> str:
    payload = {
        key: {
            "key": config.key,
            "label": config.label,
            "allowed_types": sorted(config.allowed_types),
            "accept": config.accept,
            "drop_label": config.drop_label,
            "hint": config.hint,
            "empty_label": config.empty_label,
        }
        for key, config in CONTAINERS.items()
    }
    return json.dumps(payload)


def account_name() -> str:
    for part in settings.azure_storage_connection_string.split(";"):
        if part.startswith("AccountName="):
            return part.split("=", 1)[1]
    return ""


def blob_url(container_name: str, blob_name: str) -> str:
    return f"https://{account_name()}.blob.core.windows.net/{container_name}/{blob_name}"


def download_url(container_key: str, blob_name: str) -> str:
    """Authenticated proxy link the test UI can actually open in a browser.

    The storage account has public blob access disabled, so the raw
    blob.core.windows.net URL from blob_url() 403s. This routes through
    the app's own (assessor-gated) download endpoint instead.
    """
    return f"/ui/storage/api/{container_key}/download?name={quote(blob_name, safe='')}"


def guess_content_type(
    filename: str,
    reported: str | None,
    allowed_types: frozenset[str],
) -> str:
    if reported and reported in allowed_types:
        return reported
    guessed, _ = mimetypes.guess_type(filename)
    return guessed if guessed in allowed_types else "application/octet-stream"


async def list_container_blobs(container_key: str) -> dict[str, Any]:
    config = get_container(container_key)
    if config is None:
        raise ValueError(f"Unknown container: {container_key}")
    names = await config.list_fn()
    return {
        "container": config.container_name,
        "items": [
            {"name": name, "url": download_url(container_key, name)} for name in names
        ],
    }


async def download_from_container(container_key: str, blob_name: str) -> tuple[bytes, str]:
    config = get_container(container_key)
    if config is None:
        raise ValueError(f"Unknown container: {container_key}")
    data = await download_blob(blob_name, container_name=config.container_name)
    content_type, _ = mimetypes.guess_type(blob_name)
    return data, content_type or "application/octet-stream"


async def upload_to_container(
    container_key: str,
    filename: str | None,
    reported_type: str | None,
    data: bytes,
) -> dict[str, str]:
    config = get_container(container_key)
    if config is None:
        raise ValueError(f"Unknown container: {container_key}")
    if not data:
        raise ValueError("Empty file")

    default_name = {
        "images": "image.jpg",
        "videos": "video.mp4",
        "pds-policies": "document.pdf",
    }[container_key]

    content_type = guess_content_type(
        filename or default_name,
        reported_type,
        config.allowed_types,
    )
    if content_type not in config.allowed_types:
        raise ValueError(
            f"Unsupported file type. Allowed: {', '.join(sorted(config.allowed_types))}"
        )

    original = Path(filename or default_name).name
    blob_name = f"test-uploads/{uuid.uuid4().hex}-{original}"
    url = await config.upload_fn(blob_name, data, content_type=content_type)
    return {"blob_name": blob_name, "url": url, "container": config.container_name}
