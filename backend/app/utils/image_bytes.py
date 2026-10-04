"""Validate image bytes before blob upload or VLM calls."""

from __future__ import annotations

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def detect_image_mime(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == JPEG_MAGIC:
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == PNG_MAGIC:
        return "image/png"
    return None


def is_valid_image_bytes(data: bytes) -> bool:
    return detect_image_mime(data) is not None
