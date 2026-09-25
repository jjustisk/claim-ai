"""Face detection/redaction — EgoBlur Gen1 TorchScript with OpenCV fallback."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.image_redaction import egoblur_engine

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int
    score: float = 1.0
    # Detection family — used so EgoBlur plates are never crowded out by extras
    source: str = ""


class FaceRedactor(ABC):
    @abstractmethod
    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        ...

    @abstractmethod
    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        ...


def _blur_regions(image_bgr: np.ndarray, boxes: list[BoundingBox]) -> np.ndarray:
    out = image_bgr.copy()
    for box in boxes:
        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(out.shape[1], x2), min(out.shape[0], y2)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2]
        k = max(51, (max(x2 - x1, y2 - y1) // 2) | 1)
        blurred = cv2.GaussianBlur(roi, (k, k), 0)
        out[y1:y2, x1:x2] = blurred
    return out


def _load_bgr(image_path: str | Path) -> np.ndarray:
    image = cv2.imread(str(image_path))
    if image is None:
        with Image.open(image_path) as img:
            image = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return image


def _looks_like_plate_not_face(box: BoundingBox) -> bool:
    """Licence plates are wide rectangles; faces are roughly square / portrait."""
    bw = max(1, box.x2 - box.x1)
    bh = max(1, box.y2 - box.y1)
    aspect = bw / float(bh)
    # True faces rarely exceed ~1.45 width/height; plates are typically 1.5–5
    return aspect >= 1.55


def _pad_face_box(box: BoundingBox, image_shape: tuple[int, ...], frac: float = 0.18) -> BoundingBox:
    """Expand slightly so partial / edge-cropped faces are fully covered."""
    h, w = image_shape[:2]
    bw = max(1, box.x2 - box.x1)
    bh = max(1, box.y2 - box.y1)
    pad_x = max(2, int(bw * frac))
    pad_y = max(2, int(bh * frac))
    return BoundingBox(
        x1=max(0, box.x1 - pad_x),
        y1=max(0, box.y1 - pad_y),
        x2=min(w, box.x2 + pad_x),
        y2=min(h, box.y2 + pad_y),
        score=box.score,
    )


def _filter_face_boxes(boxes: list[BoundingBox], image_shape: tuple[int, ...] | None = None) -> list[BoundingBox]:
    kept: list[BoundingBox] = []
    for box in boxes:
        if _looks_like_plate_not_face(box):
            continue
        bw = box.x2 - box.x1
        bh = box.y2 - box.y1
        # Keep small / partial faces (profile, cropped)
        if bw < 12 or bh < 12:
            continue
        if image_shape is not None:
            box = _pad_face_box(box, image_shape)
        kept.append(box)
    dropped = len(boxes) - len(kept)
    if dropped:
        logger.info("Filtered %s non-face EgoBlur box(es)", dropped)
    return kept


class EgoBlurFaceRedactor(FaceRedactor):
    """
    EgoBlur Gen1 face redactor (in-process TorchScript).

    Uses Meta EgoBlur face JIT weights when present; otherwise OpenCV Haar.
    Wide plate-like boxes are rejected (EgoBlur face often fires on number plates).
    """

    def __init__(
        self,
        model_path: str | None = None,
        score_threshold: float = 0.45,
    ) -> None:
        resolved = egoblur_engine.resolve_model_path(
            model_path,
            "ego_blur_face.jit",
            "ego_blur_face_gen1.jit",
            "ego_blur_face_gen2.jit",
        )
        self.model_path = str(resolved) if resolved else model_path
        self.score_threshold = score_threshold
        self._fallback = OpenCVFaceRedactor()

    def _egoblur_available(self) -> bool:
        return egoblur_engine.model_ready(self.model_path)

    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        if not self._egoblur_available():
            return self._fallback.detect(image_path)
        try:
            image = _load_bgr(image_path)
            detect_floor = min(self.score_threshold, 0.3)
            boxes = egoblur_engine.detect_boxes(image, self.model_path, detect_floor)
            boxes = [b for b in boxes if b.score >= self.score_threshold]
            return _filter_face_boxes(boxes, image.shape)
        except Exception as exc:
            logger.warning("EgoBlur face detect failed (%s); using OpenCV fallback", exc)
            return self._fallback.detect(image_path)

    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        input_path, output_path = Path(input_path), Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._egoblur_available():
            try:
                image = _load_bgr(input_path)
                detect_floor = min(self.score_threshold, 0.3)
                boxes = egoblur_engine.detect_boxes(image, self.model_path, detect_floor)
                boxes = [b for b in boxes if b.score >= self.score_threshold]
                boxes = _filter_face_boxes(boxes, image.shape)
                redacted = _blur_regions(image, boxes) if boxes else image
                cv2.imwrite(str(output_path), redacted)
                return boxes
            except Exception as exc:
                logger.warning("EgoBlur face redaction failed (%s); using OpenCV fallback", exc)
        return self._fallback.redact(input_path, output_path)


class OpenCVFaceRedactor(FaceRedactor):
    def __init__(self) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)

    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        image = _load_bgr(image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Lower minNeighbors / minSize to catch partial / distant faces
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.08, minNeighbors=3, minSize=(18, 18)
        )
        boxes: list[BoundingBox] = []
        for x, y, w, h in faces:
            box = BoundingBox(x1=int(x), y1=int(y), x2=int(x + w), y2=int(y + h), score=1.0)
            if _looks_like_plate_not_face(box):
                continue
            boxes.append(_pad_face_box(box, image.shape))
        profile_path = cv2.data.haarcascades + "haarcascade_profileface.xml"
        profile = cv2.CascadeClassifier(profile_path)
        if not profile.empty():
            for src in (gray, cv2.flip(gray, 1)):
                flipped = src is not gray
                hits = profile.detectMultiScale(src, scaleFactor=1.08, minNeighbors=3, minSize=(18, 18))
                iw = image.shape[1]
                for x, y, w, h in hits:
                    if flipped:
                        x = iw - x - w
                    box = BoundingBox(int(x), int(y), int(x + w), int(y + h), score=0.9)
                    if _looks_like_plate_not_face(box):
                        continue
                    boxes.append(_pad_face_box(box, image.shape))
        return boxes

    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        input_path, output_path = Path(input_path), Path(output_path)
        image = _load_bgr(input_path)
        boxes = self.detect(input_path)
        redacted = _blur_regions(image, boxes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), redacted)
        return boxes
