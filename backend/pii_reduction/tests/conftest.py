"""Shared pytest fixtures."""

from __future__ import annotations

import io
from pathlib import Path

import piexif
import pytest
from cryptography.fernet import Fernet
from PIL import Image, ImageDraw, ImageFont

from app.config.settings import Settings
from app.services.encryption.provider import FernetEncryptionProvider
from app.services.ingestion.service import ClaimService
from app.services.storage.session_store import SessionStorage


@pytest.fixture
def encryption_key() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def settings(tmp_path: Path, encryption_key: bytes, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CLAIM_AI_ENCRYPTION_KEY", encryption_key.decode("ascii"))
    # Clear cached settings / encryption
    from app.config.settings import get_settings
    from app.services.encryption.provider import get_encryption_provider

    get_settings.cache_clear()
    get_encryption_provider.cache_clear()

    s = Settings(
        data_root=tmp_path / "data",
        encryption_key=encryption_key.decode("ascii"),
        metadata_backend="pillow",
        ocr_backend="noop",
        redaction_backend="opencv",
    )
    return s


@pytest.fixture
def storage(settings: Settings, encryption_key: bytes) -> SessionStorage:
    return SessionStorage(settings, FernetEncryptionProvider(encryption_key))


@pytest.fixture
def claim_service(settings: Settings, storage: SessionStorage) -> ClaimService:
    return ClaimService(settings=settings, storage=storage)


@pytest.fixture
def image_with_gps(tmp_path: Path) -> Path:
    path = tmp_path / "damage_gps.jpg"
    img = Image.new("RGB", (400, 300), color=(180, 180, 180))
    draw = ImageDraw.Draw(img)
    draw.rectangle((50, 50, 150, 150), fill=(220, 180, 140))  # faux face region
    draw.rectangle((200, 220, 360, 270), fill=(240, 240, 40))  # faux plate region
    draw.text((210, 230), "ABC123", fill=(0, 0, 0))

    # GPS EXIF — Sydney-ish
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"S"
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = ((33, 1), (52, 1), (0, 1))
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E"
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = ((151, 1), (12, 1), (0, 1))
    exif_bytes = piexif.dump(exif_dict)
    img.save(path, "jpeg", exif=exif_bytes)
    return path


@pytest.fixture
def face_image(tmp_path: Path) -> Path:
    """Synthetic face-like oval for OpenCV cascade (may or may not detect).

    Tests that require guaranteed redaction inject AnnotatedPlateRedactor /
    draw known regions and assert pixel changes in those regions.
    """
    path = tmp_path / "face.jpg"
    img = Image.new("RGB", (300, 300), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    # Distinct face-coloured ellipse
    draw.ellipse((80, 60, 220, 220), fill=(210, 170, 140), outline=(80, 50, 40))
    draw.ellipse((120, 120, 140, 140), fill=(20, 20, 20))
    draw.ellipse((160, 120, 180, 140), fill=(20, 20, 20))
    draw.arc((120, 150, 180, 190), 0, 180, fill=(80, 40, 40), width=3)
    img.save(path, "jpeg")
    return path


@pytest.fixture
def ocr_image(tmp_path: Path) -> Path:
    path = tmp_path / "ocr_pii.png"
    img = Image.new("RGB", (500, 120), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "John Smith", fill=(0, 0, 0))
    draw.text((10, 60), "0412 123 456", fill=(0, 0, 0))
    img.save(path, "png")
    return path


@pytest.fixture
def sample_claim() -> dict:
    return {
        "claim_id": "CLM-001238",
        "customer_name": "John Smith",
        "address": "12 Maple Street, Sydney NSW",
        "date_of_birth": "1988-04-12",
        "phone": "0412 123 456",
        "email": "john@example.com",
        "claim_amount": 12450,
        "claim_description": "Water damage to kitchen",
    }
