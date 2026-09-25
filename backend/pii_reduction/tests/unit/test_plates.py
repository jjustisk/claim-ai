"""Plate detection tests — precision: plates only, blur + red outline."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services.image_redaction.faces import BoundingBox
from app.services.image_redaction.plates import (
    AnnotatedPlateRedactor,
    OpenCVPlateRedactor,
    _blur_and_outline,
)


def _draw_plate(
    img: Image.Image,
    xy: tuple[int, int, int, int],
    colour: tuple[int, int, int],
    text: str,
    text_colour: tuple[int, int, int] = (10, 10, 10),
) -> None:
    draw = ImageDraw.Draw(img)
    draw.rectangle(xy, fill=colour, outline=(20, 20, 20), width=2)
    tx = xy[0] + 8
    ty = xy[1] + max(4, (xy[3] - xy[1]) // 4)
    draw.text((tx, ty), text, fill=text_colour)


def test_yellow_plate_detected_blurred_and_outlined(tmp_path: Path):
    path = tmp_path / "yellow.jpg"
    img = Image.new("RGB", (640, 360), color=(60, 70, 80))
    _draw_plate(img, (240, 280, 420, 320), (255, 210, 0), "AB12 CDE")
    img.save(path, "jpeg", quality=95)

    redactor = OpenCVPlateRedactor()
    boxes = redactor.detect(path)
    assert len(boxes) >= 1
    assert len(boxes) <= 3
    # Must overlap the drawn plate
    assert any(b.x1 < 420 and b.x2 > 240 and b.y1 < 320 and b.y2 > 280 for b in boxes)
    # Must not be a huge slab over the whole bumper area
    for b in boxes:
        assert (b.x2 - b.x1) < 280
        assert (b.y2 - b.y1) < 80

    out = tmp_path / "yellow_out.jpg"
    redactor.redact(path, out)
    result = cv2.imread(str(out))
    # Red outline is inset inside the plate box
    b = boxes[0]
    border = result[b.y1 + 2, min(result.shape[1] - 1, (b.x1 + b.x2) // 2)]
    assert int(border[2]) > 150 and int(border[0]) < 80  # red-ish


def test_blue_plate_detected(tmp_path: Path):
    path = tmp_path / "blue.jpg"
    img = Image.new("RGB", (640, 360), color=(90, 100, 110))
    _draw_plate(img, (250, 250, 400, 295), (30, 90, 200), "HYDRGN", text_colour=(240, 240, 240))
    img.save(path, "jpeg", quality=95)

    boxes = OpenCVPlateRedactor().detect(path)
    assert boxes, "Expected blue plate detection"
    assert any(b.x1 < 400 and b.x2 > 250 and b.y1 < 295 and b.y2 > 250 for b in boxes)
    assert len(boxes) <= 3


def test_partial_plate_detected(tmp_path: Path):
    path = tmp_path / "partial.jpg"
    img = Image.new("RGB", (640, 360), color=(70, 70, 70))
    _draw_plate(img, (280, 270, 360, 310), (250, 200, 0), "LM0")
    img.save(path, "jpeg", quality=95)

    boxes = OpenCVPlateRedactor().detect(path)
    assert boxes, "Expected partial plate detection"
    assert len(boxes) <= 3


def test_blur_reduces_character_edges(tmp_path: Path):
    path = tmp_path / "cover.jpg"
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 30, 180, 70), fill=(255, 220, 0))
    draw.text((40, 40), "SECRET", fill=(0, 0, 0))
    img.save(path, "jpeg")
    image = cv2.imread(str(path))
    # Sample interior (away from inset outline)
    before = cv2.Laplacian(image[40:60, 40:160], cv2.CV_64F).var()
    covered = _blur_and_outline(image, [BoundingBox(20, 30, 180, 70)])
    after = cv2.Laplacian(covered[40:60, 40:160], cv2.CV_64F).var()
    assert after < before * 0.5


def test_blur_does_not_touch_outside_plate_box():
    """Bodywork outside the plate rectangle must be pixel-identical after redact."""
    image = np.full((120, 240, 3), 90, dtype=np.uint8)
    image[40:70, 60:180] = (0, 220, 255)  # yellow plate ROI
    # Dark glyphs so blur visibly changes interior
    image[48:62, 80:90] = (10, 10, 10)
    image[48:62, 100:110] = (10, 10, 10)
    image[48:62, 120:130] = (10, 10, 10)
    image[10:20, 10:30] = (40, 180, 40)  # marker outside plate
    before_outside = image.copy()
    box = BoundingBox(60, 40, 180, 70)
    out = _blur_and_outline(image, [box])
    # Outside: unchanged
    mask = np.ones(image.shape[:2], dtype=bool)
    mask[40:70, 60:180] = False
    assert np.array_equal(out[mask], before_outside[mask])
    # Outside marker untouched
    assert np.array_equal(out[10:20, 10:30], before_outside[10:20, 10:30])
    # Inside plate glyphs: changed (blurred)
    assert not np.array_equal(out[48:62, 80:130], before_outside[48:62, 80:130])


def test_no_false_plates_on_blank_car_body(tmp_path: Path):
    """Uniform panels without plate colour/text must not produce detections."""
    path = tmp_path / "body.jpg"
    img = Image.new("RGB", (640, 360), color=(180, 180, 185))
    draw = ImageDraw.Draw(img)
    # Chrome-like horizontal strip (not a plate)
    draw.rectangle((100, 200, 500, 230), fill=(200, 200, 205))
    img.save(path, "jpeg", quality=95)
    boxes = OpenCVPlateRedactor().detect(path)
    assert boxes == []


def test_closeup_white_plate_detected(tmp_path: Path):
    """Wide, centred white plates in close-up claim photos must not be size-rejected."""
    path = tmp_path / "white_closeup.jpg"
    img = Image.new("RGB", (400, 520), color=(40, 70, 140))
    draw = ImageDraw.Draw(img)
    # ~40% of frame width — previously rejected by the 45% width / 4% area caps
    draw.rectangle((120, 280, 280, 320), fill=(245, 245, 245), outline=(20, 20, 20), width=2)
    # Blocky glyphs so MSER / edge structure fires (default PIL font is too thin)
    for i in range(7):
        x = 130 + i * 20
        draw.rectangle((x, 288, x + 12, 312), fill=(10, 10, 10))
        draw.rectangle((x + 3, 292, x + 9, 296), fill=(245, 245, 245))
    img.save(path, "jpeg", quality=95)

    boxes = OpenCVPlateRedactor().detect(path)
    assert boxes, "Expected close-up white plate detection"
    assert any(b.x1 < 280 and b.x2 > 120 and b.y1 < 320 and b.y2 > 280 for b in boxes)


def test_wide_plate_on_white_vehicle_detected(tmp_path: Path):
    """White plate on a white body must still be found (not merged away)."""
    path = tmp_path / "white_on_white.jpg"
    img = Image.new("RGB", (900, 600), color=(235, 235, 235))
    draw = ImageDraw.Draw(img)
    # Vehicle body mass
    draw.rectangle((200, 180, 750, 520), fill=(250, 250, 250))
    # NSW-style plate: blue strip + white field + dark glyphs
    draw.rectangle((520, 430, 690, 470), fill=(250, 250, 250), outline=(20, 20, 20), width=2)
    draw.rectangle((520, 430, 545, 470), fill=(30, 90, 200))
    draw.text((555, 440), "HYDRGN", fill=(10, 10, 10))
    img.save(path, "jpeg", quality=95)

    boxes = OpenCVPlateRedactor().detect(path)
    assert boxes, "Expected white-on-white plate detection"
    assert any(b.x1 < 690 and b.x2 > 520 and b.y1 < 470 and b.y2 > 430 for b in boxes)


def test_annotated_redactor_still_works(tmp_path: Path):
    path = tmp_path / "ann.jpg"
    Image.new("RGB", (100, 100), color=(40, 40, 40)).save(path, "jpeg")
    out = tmp_path / "ann_out.jpg"
    boxes = AnnotatedPlateRedactor([BoundingBox(10, 10, 60, 40)]).redact(path, out)
    assert len(boxes) == 1
    assert out.exists()
    result = cv2.imread(str(out))
    # Red outline on top edge
    assert int(result[10, 35][2]) > 150


def test_egoblur_boxes_not_crowded_out_by_extras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When EgoBlur finds a plate, extras must not flood the image."""
    from app.services.image_redaction.plates import EgoBlurPlateRedactor

    path = tmp_path / "merge.jpg"
    Image.new("RGB", (447, 447), color=(80, 80, 90)).save(path, "jpeg")

    ego = [BoundingBox(306, 240, 415, 292, score=0.985, source="egoblur")]
    noise = [
        BoundingBox(244, 218, 287, 235, score=0.74, source="colour"),
        BoundingBox(333, 279, 400, 293, score=0.74, source="colour"),
        BoundingBox(20, 145, 197, 203, score=0.74, source="colour"),
        BoundingBox(162, 187, 184, 195, score=2.628, source="opencv"),
    ]

    redactor = EgoBlurPlateRedactor(model_path=None, score_threshold=0.55)

    class _FakeFallback:
        def detect(self, _path: Path) -> list[BoundingBox]:
            return list(noise)

    redactor._fallback = _FakeFallback()  # type: ignore[assignment]
    monkeypatch.setattr(
        "app.services.image_redaction.plate_layers.detect_ocr_plates",
        lambda _img: [],
    )
    image = cv2.imread(str(path))
    merged = redactor._merge_layers(image, path, ego)
    assert len(merged) == 1
    assert merged[0].x1 == 306 and merged[0].y1 == 240
    assert (merged[0].source or "").startswith("egoblur")
