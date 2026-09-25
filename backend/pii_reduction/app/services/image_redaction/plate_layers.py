"""Additional plate-detection layers (Haar, morphology, OCR, colour rectangles).

These are recall-oriented supplements to EgoBlur + MSER. Bounding boxes are
unioned and NMS'd by the plate redactor — they never replace EgoBlur.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import cv2
import numpy as np

from app.services.image_redaction.faces import BoundingBox

logger = logging.getLogger(__name__)

# AU / NZ / EU / UK-ish plate tokens (used when OCR is available)
_PLATE_TOKEN_RE = re.compile(
    r"^(?:"
    r"[A-Z]{1,3}[-\s]?\d{1,3}[-\s]?[A-Z]{0,3}"
    r"|\d[A-Z]{1,3}[-\s]?\d{2,4}"
    r"|[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{2}"
    r"|[A-Z]{3}[-\s]?\d{3}"
    r"|[A-Z]{5,7}"  # demo plates e.g. XXXXX / HYDRGN
    r")$"
)


def _aspect_ok(bw: int, bh: int) -> bool:
    if bw < 16 or bh < 7:
        return False
    aspect = bw / float(bh)
    return 1.25 <= aspect <= 8.5


@lru_cache(maxsize=1)
def _haar_cascade() -> cv2.CascadeClassifier | None:
    path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        logger.warning("Haar plate cascade missing at %s", path)
        return None
    return cascade


def detect_haar_plates(image_bgr: np.ndarray) -> list[BoundingBox]:
    cascade = _haar_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    boxes: list[BoundingBox] = []
    for scale, neigh in ((1.05, 3), (1.12, 4)):
        try:
            hits = cascade.detectMultiScale(
                gray, scaleFactor=scale, minNeighbors=neigh, minSize=(24, 10)
            )
        except cv2.error:
            continue
        for x, y, w, h in hits:
            if _aspect_ok(int(w), int(h)):
                boxes.append(
                    BoundingBox(
                        int(x), int(y), int(x + w), int(y + h), score=0.72, source="haar"
                    )
                )
    return boxes


def detect_morph_plates(image_bgr: np.ndarray) -> list[BoundingBox]:
    """Classic ALPR locator: vertical edges + rectangular close."""
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 40, 40)
    sobel = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel = np.uint8(np.clip(np.abs(sobel) / (np.max(np.abs(sobel)) + 1e-6) * 255, 0, 255))
    _, thresh = cv2.threshold(sobel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(13, w // 40), 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    closed = cv2.morphologyEx(
        closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    )
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[BoundingBox] = []
    img_area = float(max(1, w * h))
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if not _aspect_ok(bw, bh):
            continue
        area = (bw * bh) / img_area
        if area < 0.0003 or area > 0.18:
            continue
        roi = gray[y : y + bh, x : x + bw]
        if roi.size < 80 or float(roi.std()) < 14:
            continue
        boxes.append(BoundingBox(x, y, x + bw, y + bh, score=0.62, source="morph"))
    return boxes


def detect_colour_rectangles(image_bgr: np.ndarray) -> list[BoundingBox]:
    """Yellow / white / blue / red plate-coloured rectangles with glyph energy."""
    h, w = image_bgr.shape[:2]
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    masks = [
        (cv2.inRange(hsv, (8, 40, 50), (40, 255, 255)), 0.78),  # yellow
        (cv2.inRange(hsv, (0, 0, 155), (180, 55, 255)), 0.74),  # white
        (cv2.inRange(hsv, (95, 50, 40), (135, 255, 255)), 0.7),  # blue
        (
            cv2.bitwise_or(
                cv2.inRange(hsv, (0, 70, 50), (12, 255, 255)),
                cv2.inRange(hsv, (160, 70, 50), (180, 255, 255)),
            ),
            0.76,
        ),  # red EU / demo plates
    ]
    boxes: list[BoundingBox] = []
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
    img_area = float(max(1, w * h))
    for mask, score in masks:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            if not _aspect_ok(bw, bh):
                continue
            area = (bw * bh) / img_area
            if area < 0.0003 or area > 0.18:
                continue
            purity = float(np.count_nonzero(closed[y : y + bh, x : x + bw])) / float(
                max(1, bw * bh)
            )
            if purity < 0.18:
                continue
            roi = gray[y : y + bh, x : x + bw]
            if roi.size < 80 or float(roi.std()) < 12:
                continue
            boxes.append(BoundingBox(x, y, x + bw, y + bh, score=score, source="colour"))
    return boxes


def detect_ocr_plates(image_bgr: np.ndarray) -> list[BoundingBox]:
    """Last-resort layer: Tesseract tokens that look like plate numbers."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return []

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    try:
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
    except Exception as exc:  # noqa: BLE001
        logger.debug("OCR plate layer skipped: %s", exc)
        return []

    boxes: list[BoundingBox] = []
    n = len(data.get("text", []))
    for i in range(n):
        raw = (data["text"][i] or "").strip().upper()
        token = re.sub(r"[^A-Z0-9-]", "", raw)
        if len(token) < 3:
            continue
        if not _PLATE_TOKEN_RE.match(token.replace("-", "")) and not _PLATE_TOKEN_RE.match(
            token
        ):
            # Accept alnum blobs that look plate-like (mix of letters+digits, or 5+ caps)
            letters = sum(c.isalpha() for c in token)
            digits = sum(c.isdigit() for c in token)
            if not (
                (letters >= 2 and digits >= 1 and 4 <= len(token) <= 9)
                or (letters >= 5 and digits == 0 and len(token) <= 8)
            ):
                continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 20:
            continue
        x, y, bw, bh = (
            int(data["left"][i]),
            int(data["top"][i]),
            int(data["width"][i]),
            int(data["height"][i]),
        )
        # Pad so glyphs are fully covered
        pad_x, pad_y = max(4, bw // 8), max(3, bh // 6)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = x + bw + pad_x
        y2 = y + bh + pad_y
        if _aspect_ok(x2 - x1, y2 - y1) or (letters >= 4):
            boxes.append(BoundingBox(x1, y1, x2, y2, score=0.68, source="ocr"))
    return boxes


def detect_all_extra_layers(image_bgr: np.ndarray) -> list[BoundingBox]:
    boxes: list[BoundingBox] = []
    for fn in (detect_haar_plates, detect_morph_plates, detect_colour_rectangles, detect_ocr_plates):
        try:
            boxes.extend(fn(image_bgr))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Plate layer %s failed: %s", fn.__name__, exc)
    return boxes
