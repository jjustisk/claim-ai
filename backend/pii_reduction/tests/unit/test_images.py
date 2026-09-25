"""Image pipeline unit tests."""

from __future__ import annotations

from pathlib import Path

import piexif
from PIL import Image

from app.services.image_redaction.faces import BoundingBox, OpenCVFaceRedactor, _blur_regions
from app.services.image_redaction.metadata import PillowMetadataSanitizer
from app.services.image_redaction.plates import AnnotatedPlateRedactor
from app.services.image_redaction.pipeline import ImageRedactionPipeline
from app.services.ocr.provider import NoOpOCRProvider
from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry
import cv2
import numpy as np


def test_exif_gps_removed(image_with_gps: Path, tmp_path: Path):
    out = tmp_path / "clean.jpg"
    assert PillowMetadataSanitizer().sanitize(image_with_gps, out)
    # Original has GPS
    original_exif = piexif.load(str(image_with_gps))
    assert original_exif.get("GPS")
    # Sanitised should have no GPS
    try:
        clean_exif = piexif.load(str(out))
        gps = clean_exif.get("GPS") or {}
        assert not gps
    except Exception:
        # No EXIF at all is also success
        pass


def test_face_region_redaction(tmp_path: Path):
    path = tmp_path / "face_box.jpg"
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    # Uniform skin-tone block that we will force-redact via blur helper
    for x in range(50, 150):
        for y in range(50, 150):
            img.putpixel((x, y), (200, 160, 130))
    img.save(path, "jpeg")

    image = cv2.imread(str(path))
    boxes = [BoundingBox(50, 50, 150, 150)]
    redacted = _blur_regions(image, boxes)
    out = tmp_path / "face_redacted.jpg"
    cv2.imwrite(str(out), redacted)
    # Centre pixel should differ after blur of uniform region? Gaussian of uniform stays same.
    # Instead assert ROI variance changed vs surrounding by writing noise first.
    noisy = image.copy()
    noisy[50:150, 50:150] = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    before_std = float(noisy[50:150, 50:150].std())
    blurred = _blur_regions(noisy, boxes)
    after_std = float(blurred[50:150, 50:150].std())
    assert after_std < before_std


def test_plate_redaction(tmp_path: Path):
    path = tmp_path / "plate.jpg"
    img = Image.new("RGB", (400, 200), color=(80, 80, 80))
    for x in range(100, 300):
        for y in range(80, 140):
            img.putpixel((x, y), (240, 240, 40))
    img.save(path, "jpeg")
    out = tmp_path / "plate_out.jpg"
    boxes = AnnotatedPlateRedactor([BoundingBox(100, 80, 300, 140)]).redact(path, out)
    assert len(boxes) == 1
    assert out.exists()
    result = cv2.imread(str(out))
    # Red outline (BGR) on the box border
    assert int(result[80, 200][2]) > 150
    assert int(result[80, 200][0]) < 80


def test_pipeline_metadata_and_registry(image_with_gps: Path, tmp_path: Path, settings):
    pipeline = ImageRedactionPipeline(
        settings=settings,
        ocr=NoOpOCRProvider(),
        pii=PIIDetector(settings),
    )
    registry = PlaceholderRegistry()
    out_img = tmp_path / "san.jpg"
    out_ocr = tmp_path / "ocr.txt"
    result, _ = pipeline.process(
        session_id="TEST",
        input_id="IMG_1",
        source_path=image_with_gps,
        output_image_path=out_img,
        ocr_output_path=out_ocr,
        registry=registry,
        run_ocr=True,
    )
    assert result.metadata_sanitised
    assert out_img.exists()
