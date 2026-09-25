"""OCR word boxes → PII detection → in-image blur (house numbers, signs, mail)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import cv2
import numpy as np

from app.services.image_redaction.faces import BoundingBox, _blur_regions
from app.services.ocr.provider import OCRProvider
from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry

logger = logging.getLogger(__name__)

_HOUSE_OR_STREET = re.compile(
    r"\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+\s+){0,3}"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Court|Ct|"
    r"Place|Pl|Parade|Pde|Crescent|Cres|Boulevard|Blvd|Highway|Hwy|"
    r"Terrace|Tce|Way|Close|Cl)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE = re.compile(r"\b(?:\+?61\s?4|04)\d{2}[\s-]?\d{3}[\s-]?\d{3}\b")
_PLATEISH = re.compile(r"\b[A-Z]{1,3}\d{1,3}[A-Z]{0,3}\b")
_NAMEISH = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b")


def _regex_sensitive(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2:
        return False
    if _EMAIL.search(t) or _PHONE.search(t) or _HOUSE_OR_STREET.search(t):
        return True
    compact = t.replace(" ", "").replace("-", "").upper()
    if _PLATEISH.fullmatch(compact) and any(c.isdigit() for c in t):
        return True
    return False


def _union_boxes(boxes: list[BoundingBox]) -> BoundingBox | None:
    if not boxes:
        return None
    return BoundingBox(
        x1=min(b.x1 for b in boxes),
        y1=min(b.y1 for b in boxes),
        x2=max(b.x2 for b in boxes),
        y2=max(b.y2 for b in boxes),
        score=1.0,
        source="ocr_text",
    )


class InImageTextMasker:
    """Blur on-image PII (street numbers, names, mail) using OCR word boxes."""

    def __init__(self, ocr: OCRProvider, pii: PIIDetector) -> None:
        self.ocr = ocr
        self.pii = pii

    def mask(
        self,
        image_bgr: np.ndarray,
        registry: PlaceholderRegistry,
    ) -> tuple[np.ndarray, list[BoundingBox], str]:
        words = self.ocr.extract_words(image_bgr)
        boxes: list[BoundingBox] = []
        pieces: list[str] = []
        lines: dict[int, list[dict]] = {}

        # Fast path: regex only per word (Presidio-per-word was a major CPU sink)
        for word in words:
            text = word.get("text") or ""
            line_no = int(word.get("line", 0))
            lines.setdefault(line_no, []).append(word)
            if _regex_sensitive(text):
                boxes.append(
                    BoundingBox(
                        x1=int(word["x"]),
                        y1=int(word["y"]),
                        x2=int(word["x"] + word["w"]),
                        y2=int(word["y"] + word["h"]),
                        score=1.0,
                        source="ocr_text",
                    )
                )
                sanitised, _ = self.pii.sanitize_text(text, registry)
                pieces.append(sanitised)
            else:
                pieces.append(text)

        # One Presidio pass per OCR line (names / addresses spanning words)
        for line_words in lines.values():
            line = " ".join((w.get("text") or "") for w in line_words).strip()
            if len(line) < 4:
                continue
            needs = _regex_sensitive(line) or bool(_NAMEISH.search(line))
            line_hits = self.pii.detect(line) if needs or len(line.split()) >= 2 else []
            if not (_HOUSE_OR_STREET.search(line) or line_hits):
                continue
            sanitised, _ = self.pii.sanitize_text(line, registry)
            if sanitised == line and not _HOUSE_OR_STREET.search(line):
                continue
            line_boxes = [
                BoundingBox(
                    x1=int(w["x"]),
                    y1=int(w["y"]),
                    x2=int(w["x"] + w["w"]),
                    y2=int(w["y"] + w["h"]),
                    score=1.0,
                    source="ocr_text",
                )
                for w in line_words
                if w.get("w") and w.get("h")
            ]
            united = _union_boxes(line_boxes)
            if united is not None:
                boxes.append(united)

        if boxes:
            image_bgr = _blur_regions(image_bgr, boxes)
        sanitised_ocr = " ".join(p for p in pieces if p).strip()
        if not sanitised_ocr and words:
            # Avoid a second full Tesseract pass — join what we already OCR'd
            sanitised_ocr, _ = self.pii.sanitize_text(
                " ".join((w.get("text") or "") for w in words), registry
            )
        return image_bgr, boxes, sanitised_ocr

    def mask_path(
        self,
        input_path: str | Path,
        output_path: str | Path,
        registry: PlaceholderRegistry,
    ) -> tuple[list[BoundingBox], str]:
        image = cv2.imread(str(input_path))
        if image is None:
            from PIL import Image

            with Image.open(input_path) as img:
                image = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        redacted, boxes, text = self.mask(image, registry)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), redacted)
        return boxes, text
