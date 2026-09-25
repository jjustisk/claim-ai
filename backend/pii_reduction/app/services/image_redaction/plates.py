"""Licence plate detection/redaction — EgoBlur Gen1 + OpenCV MSER fallback."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.image_redaction import egoblur_engine
from app.services.image_redaction.faces import BoundingBox
from app.services.image_redaction.plate_layers import detect_ocr_plates

logger = logging.getLogger(__name__)

# BGR red for detection outline
_OUTLINE_BGR = (0, 0, 255)


def _load_bgr(image_path: str | Path) -> np.ndarray:
    image = cv2.imread(str(image_path))
    if image is None:
        with Image.open(image_path) as img:
            image = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return image


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (a.x2 - a.x1) * (a.y2 - a.y1))
    area_b = max(1, (b.x2 - b.x1) * (b.y2 - b.y1))
    return inter / float(area_a + area_b - inter)


def _plate_quality(box: BoundingBox) -> float:
    """Rank overlapping candidates without letting OpenCV extras beat EgoBlur."""
    bw = max(1, box.x2 - box.x1)
    bh = max(1, box.y2 - box.y1)
    aspect = bw / float(bh)
    area = float(bw * bh)
    if 2.2 <= aspect <= 5.2:
        q = 2.4
    elif 1.6 <= aspect <= 6.8:
        q = 1.4
    elif 1.25 <= aspect <= 8.5:
        q = 0.6
    else:
        q = 0.0
    # Mild preference for reasonably sized plates (not micro-fragments)
    if 1500 <= area <= 40000:
        q += 0.6
    elif 600 <= area < 1500 or 40000 < area <= 80000:
        q += 0.25
    else:
        # Tiny MSER chips score high on "tight box" previously — demote them
        q += 0.15 / (1.0 + area / 8000.0)

    src = (box.source or "").lower()
    if src.startswith("egoblur") or (not src and 0.0 <= box.score <= 1.2):
        # EgoBlur is calibrated 0–1 and is the primary detector — always rank above extras
        q += 4.0 + float(box.score)
    elif src in {"opencv", "haar", "morph", "colour", "ocr"}:
        q += min(1.2, float(box.score) / 3.0)
    elif 0.0 <= box.score <= 1.2:
        q += 3.5 + float(box.score)
    else:
        q += min(1.0, float(box.score) / 4.0)
    return q


def _nms(boxes: list[BoundingBox], iou_thresh: float = 0.2) -> list[BoundingBox]:
    ordered = sorted(boxes, key=_plate_quality, reverse=True)
    kept: list[BoundingBox] = []
    for box in ordered:
        if any(_iou(box, k) >= iou_thresh for k in kept):
            continue
        kept.append(box)
    return kept


def _clamp_box(box: BoundingBox, image_shape: tuple[int, ...]) -> BoundingBox:
    """Keep the detection box as-is (no expansion onto bodywork)."""
    h, w = image_shape[:2]
    x1 = max(0, min(w - 1, box.x1))
    y1 = max(0, min(h - 1, box.y1))
    x2 = max(x1 + 1, min(w, box.x2))
    y2 = max(y1 + 1, min(h, box.y2))
    return BoundingBox(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        score=box.score,
        source=getattr(box, "source", "") or "",
    )


def _tight_pad(box: BoundingBox, image_shape: tuple[int, ...]) -> BoundingBox:
    """Legacy name — clamps only; does not expand beyond the detected plate."""
    return _clamp_box(box, image_shape)


def _red_fraction(hsv: np.ndarray, x: int, y: int, bw: int, bh: int) -> float:
    roi = hsv[y : y + bh, x : x + bw]
    if roi.size == 0:
        return 0.0
    r1 = cv2.inRange(roi, (0, 70, 50), (12, 255, 255))
    r2 = cv2.inRange(roi, (160, 70, 50), (180, 255, 255))
    return float((r1.mean() + r2.mean()) / (2.0 * 255.0))


def _looks_like_brake_light(
    hsv: np.ndarray,
    x: int,
    y: int,
    bw: int,
    bh: int,
    gray: np.ndarray | None = None,
) -> bool:
    """Red lamp clusters (taillights) — never treat wide / glyph-rich red plates as lights."""
    aspect = bw / float(max(1, bh))
    # Number plates are wide rectangles (incl. red EU / demo plates like XXXXX)
    if aspect >= 1.7:
        return False
    if gray is not None and _has_character_structure(gray, x, y, bw, bh):
        return False
    yf, bf, wf = _colour_fractions(hsv, x, y, bw, bh)
    rf = _red_fraction(hsv, x, y, bw, bh)
    if rf >= 0.28 and yf < 0.12 and wf < 0.25 and bf < 0.08:
        return True
    if rf >= 0.45 and aspect < 1.7:
        return True
    return False


def _refine_plate_box(box: BoundingBox, gray: np.ndarray, hsv: np.ndarray) -> BoundingBox:
    """Shrink a loose box to the high-contrast core (colour-agnostic)."""
    h, w = gray.shape[:2]
    x1, y1, x2, y2 = _clamp_box(box, (h, w)).x1, box.y1, box.x2, box.y2
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 16 or y2 - y1 < 8:
        return _clamp_box(box, (h, w))

    roi_hsv = hsv[y1:y2, x1:x2]
    roi_gray = gray[y1:y2, x1:x2]
    # Any saturated plate paint + edges (yellow/white/blue/red demo plates)
    yellow = cv2.inRange(roi_hsv, (8, 35, 50), (40, 255, 255))
    blue = cv2.inRange(roi_hsv, (95, 55, 40), (130, 255, 255))
    white = cv2.inRange(roi_hsv, (0, 0, 140), (180, 80, 255))
    red1 = cv2.inRange(roi_hsv, (0, 50, 50), (12, 255, 255))
    red2 = cv2.inRange(roi_hsv, (160, 50, 50), (180, 255, 255))
    edges = cv2.Canny(roi_gray, 60, 160)
    mask = yellow
    for m in (blue, white, red1, red2, edges):
        mask = cv2.bitwise_or(mask, m)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    ys, xs = np.where(mask > 0)
    if len(xs) < 30:
        return _clamp_box(box, (h, w))

    x_lo, x_hi = np.percentile(xs, [4, 96]).astype(int)
    y_lo, y_hi = np.percentile(ys, [6, 94]).astype(int)
    nx1 = x1 + int(x_lo)
    ny1 = y1 + int(y_lo)
    nx2 = x1 + int(x_hi) + 1
    ny2 = y1 + int(y_hi) + 1
    nx1, ny1 = max(x1, nx1), max(y1, ny1)
    nx2, ny2 = min(x2, nx2), min(y2, ny2)
    if nx2 - nx1 < 20 or ny2 - ny1 < 8:
        return _clamp_box(box, (h, w))
    aspect = (nx2 - nx1) / float(ny2 - ny1)
    if aspect < 1.35 or aspect > 7.0:
        return _clamp_box(box, (h, w))
    return BoundingBox(
        x1=nx1,
        y1=ny1,
        x2=nx2,
        y2=ny2,
        score=box.score,
        source=getattr(box, "source", "") or "",
    )


def _egoblur_box_ok(box: BoundingBox, img_w: int, img_h: int, min_score: float) -> bool:
    if box.score < min_score:
        return False
    bw = box.x2 - box.x1
    bh = box.y2 - box.y1
    # Allow compact / partial plates (e.g. UK yellow van plates ~1.5–1.7)
    if bw < 14 or bh < 7:
        return False
    aspect = bw / float(bh)
    if not (1.2 <= aspect <= 8.5):
        return False
    area = (bw * bh) / float(max(1, img_w * img_h))
    if area < 0.00025 or area > 0.22:
        return False
    return True


def _blur_and_outline(image_bgr: np.ndarray, boxes: list[BoundingBox]) -> np.ndarray:
    """Blur strictly inside each plate rectangle; leave the rest of the car untouched."""
    out = image_bgr.copy()
    for box in boxes:
        x1, y1 = max(0, box.x1), max(0, box.y1)
        x2, y2 = min(out.shape[1], box.x2), min(out.shape[0], box.y2)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2].copy()
        bw, bh = x2 - x1, y2 - y1
        # Strong blur confined to the plate ROI (assignment never leaves this rectangle)
        k = max(31, (max(bw, bh) // 2) | 1)
        if k % 2 == 0:
            k += 1
        k = min(k, max(3, ((min(bw, bh) * 2) - 1) | 1))
        out[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
        # Outline inset so paint stays on the plate, not the bumper
        if bw > 4 and bh > 4:
            cv2.rectangle(out, (x1 + 1, y1 + 1), (x2 - 2, y2 - 2), _OUTLINE_BGR, thickness=2)
    return out


def _cover_regions(image_bgr: np.ndarray, boxes: list[BoundingBox]) -> np.ndarray:
    return _blur_and_outline(image_bgr, boxes)


def _plate_geometry_ok(bw: int, bh: int, img_w: int, img_h: int, *, partial: bool) -> bool:
    if bw < 20 or bh < 8:
        return False
    aspect = bw / float(bh)
    if partial:
        if not (1.3 <= aspect <= 7.5):
            return False
    elif not (1.8 <= aspect <= 6.0):
        return False
    # Allow close-up claim photos where the plate fills much of the frame
    if bh > img_h * 0.35 or bw > img_w * 0.85:
        return False
    area_ratio = (bw * bh) / float(img_w * img_h)
    if area_ratio < 0.00025 or area_ratio > 0.15:
        return False
    return True


def _has_character_structure(gray: np.ndarray, x: int, y: int, bw: int, bh: int) -> bool:
    """Plates have vertical character strokes / alternating ink — body panels do not."""
    roi = gray[y : y + bh, x : x + bw]
    if roi.size < 80:
        return False
    sobel_x = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    edge_energy = float(np.mean(np.abs(sobel_x)))
    col_profile = roi.mean(axis=0)
    col_std = float(np.std(col_profile))
    return edge_energy >= 12.0 and col_std >= 6.0 and float(roi.std()) >= 16.0


def _dark_ink_ratio(gray: np.ndarray, x: int, y: int, bw: int, bh: int) -> float:
    roi = gray[y : y + bh, x : x + bw]
    if roi.size == 0:
        return 0.0
    thresh = float(np.median(roi)) - 25.0
    thresh = max(40.0, min(140.0, thresh))
    return float(np.count_nonzero(roi < thresh)) / float(roi.size)


def _colour_fractions(hsv: np.ndarray, x: int, y: int, bw: int, bh: int) -> tuple[float, float, float]:
    roi = hsv[y : y + bh, x : x + bw]
    if roi.size == 0:
        return 0.0, 0.0, 0.0
    yellow = cv2.inRange(roi, (8, 35, 50), (40, 255, 255))
    blue = cv2.inRange(roi, (95, 55, 40), (130, 255, 255))
    white = cv2.inRange(roi, (0, 0, 145), (180, 75, 255))
    scale = 255.0
    return yellow.mean() / scale, blue.mean() / scale, white.mean() / scale


def _score_candidate(
    *,
    x: int,
    y: int,
    bw: int,
    bh: int,
    img_w: int,
    img_h: int,
    gray: np.ndarray,
    hsv: np.ndarray,
    base: float,
) -> float | None:
    """Return an uncapped ranking score (higher = better). Do not clamp to 1.0."""
    if not _plate_geometry_ok(bw, bh, img_w, img_h, partial=True):
        return None
    cy = (y + bh / 2.0) / float(img_h)
    cx = (x + bw / 2.0) / float(img_w)
    if cy < 0.06:
        return None
    if not _has_character_structure(gray, x, y, bw, bh):
        return None
    ink = _dark_ink_ratio(gray, x, y, bw, bh)
    if ink < 0.035:
        return None
    roi = gray[y : y + bh, x : x + bw]
    contrast = float(roi.std())
    if contrast < 16.0:
        return None

    aspect = bw / float(bh)
    area = (bw * bh) / float(img_w * img_h)
    yf, bf, wf = _colour_fractions(hsv, x, y, bw, bh)

    score = base
    # Aspect: true plates are wide rectangles
    if 2.4 <= aspect <= 5.0:
        score += 0.35
    elif 2.0 <= aspect < 2.4 or 5.0 < aspect <= 6.0:
        score += 0.15
    elif 1.7 <= aspect < 2.0:
        score += 0.05

    # Vertical position on vehicle body (not sky / not footer graphics)
    if 0.45 <= cy <= 0.75:
        score += 0.4
    elif 0.38 <= cy < 0.45 or 0.75 < cy <= 0.88:
        score += 0.15
    elif cy > 0.92:
        score -= 0.25  # footer logos / bottom banners

    # Prefer subject-centred plates
    if abs(cx - 0.5) <= 0.18:
        score += 0.25
    elif abs(cx - 0.5) <= 0.3:
        score += 0.1
    if cx < 0.1 or cx > 0.9:
        score -= 0.35

    # Readable plate size (not tiny noise, not bumper-wide slab)
    if 0.004 <= area <= 0.04:
        score += 0.35
    elif 0.002 <= area < 0.004 or 0.04 < area <= 0.06:
        score += 0.1
    elif area > 0.06:
        score -= 0.2

    if 0.08 <= ink <= 0.45:
        score += 0.15
    score += min(0.2, contrast / 200.0)

    # Colour evidence. Yellow alone is weak (brake lights / reflectors); require
    # plate-like size/aspect before giving the full yellow bonus.
    rf = _red_fraction(hsv, x, y, bw, bh)
    if yf >= 0.2 and aspect >= 1.8 and area >= 0.0015:
        score += 0.4
    elif yf >= 0.12 and aspect >= 2.0:
        score += 0.18
    if rf >= 0.25 and aspect >= 1.7:
        score += 0.45  # red EU / demo plates
    elif rf >= 0.15 and aspect >= 2.0:
        score += 0.2
    if bf >= 0.08:
        score += 0.28
    elif bf >= 0.04:
        score += 0.1
    if wf >= 0.45:
        score += 0.4
    elif wf >= 0.3:
        score += 0.2

    # Side amber blobs without a pale plate field are usually lights, not plates
    if yf >= 0.2 and wf < 0.15 and abs(cx - 0.5) > 0.25:
        score -= 0.4

    # Taillights / brake lamps
    if _looks_like_brake_light(hsv, x, y, bw, bh, gray):
        return None

    # Large pale slabs (insurance notices, body panels) without yellow/blue plate paint
    if wf >= 0.65 and yf < 0.08 and bf < 0.08 and area > 0.012:
        score -= 0.45

    # Reward compact glyph density (MSER often returns slightly loose boxes)
    fill_proxy = min(1.0, (bw * bh) / float(max(1, (bw + 4) * (bh + 4))))
    score += 0.05 * fill_proxy
    return score


class PlateRedactor(ABC):
    @abstractmethod
    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        ...

    @abstractmethod
    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        ...


class EgoBlurPlateRedactor(PlateRedactor):
    """Multi-layer plate redactor: EgoBlur first; extras only if EgoBlur finds nothing."""

    MAX_BOXES = 4
    EGO_TRUST_SCORE = 0.45

    def __init__(
        self,
        model_path: str | None = None,
        score_threshold: float = 0.55,
    ) -> None:
        resolved = egoblur_engine.resolve_model_path(
            model_path,
            "ego_blur_lp.jit",
            "ego_blur_lp_gen1.jit",
            "ego_blur_lp_gen2.jit",
        )
        self.model_path = str(resolved) if resolved else model_path
        self.score_threshold = score_threshold
        self._fallback = OpenCVPlateRedactor()

    def _egoblur_available(self) -> bool:
        ready = egoblur_engine.model_ready(self.model_path)
        if self.model_path and Path(self.model_path).is_file() and not egoblur_engine.egoblur_runtime_available():
            logger.error(
                "EgoBlur LP model present at %s but torch/torchvision missing — "
                "OpenCV fallback will be used (expect more false positives). "
                "Install torch into the API virtualenv.",
                self.model_path,
            )
        return ready

    def _postprocess(self, image: np.ndarray, boxes: list[BoundingBox]) -> list[BoundingBox]:
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        kept: list[BoundingBox] = []
        for box in boxes:
            box = _clamp_box(box, image.shape)
            min_score = min(self.score_threshold, 0.15)
            if not _egoblur_box_ok(box, w, h, min_score):
                continue
            if _looks_like_brake_light(hsv, box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1, gray):
                continue
            refined = _refine_plate_box(box, gray, hsv)
            # Keep original if refine over-shrinks a valid detection
            if _egoblur_box_ok(refined, w, h, min_score):
                refined.source = "egoblur"
                kept.append(refined)
            else:
                box.source = "egoblur"
                kept.append(box)
        kept = _nms(kept, iou_thresh=0.3)
        kept.sort(key=lambda b: b.score, reverse=True)
        return kept[: self.MAX_BOXES]

    def _egoblur_multiscale(self, image: np.ndarray) -> list[BoundingBox]:
        """Progressive EgoBlur: full frame → bumper → optional upscale. Stop early on hit."""
        if not self.model_path:
            return []
        detect_floor = min(self.score_threshold, 0.15)
        trust = max(self.score_threshold, self.EGO_TRUST_SCORE)
        h, w = image.shape[:2]

        # Ordered cheapest → more expensive. Skip CLAHE / 2×2 tiles (were ~6–8× slower).
        variants: list[tuple[np.ndarray, float, int, int]] = [
            (image, 1.0, 0, 0),
        ]
        y0 = int(h * 0.28)
        bumper = image[y0:h, :]
        if bumper.size and bumper.shape[0] > 40:
            variants.append((bumper, 1.0, 0, y0))
        # Distant plates only: one modest upscale when the frame is not already huge
        if max(h, w) < 1600:
            up = 1.45
            variants.append(
                (
                    cv2.resize(image, None, fx=up, fy=up, interpolation=cv2.INTER_LINEAR),
                    up,
                    0,
                    0,
                )
            )

        raw: list[BoundingBox] = []
        for view, scale, ox, oy in variants:
            try:
                found = egoblur_engine.detect_boxes(view, self.model_path, detect_floor)
            except Exception as exc:  # noqa: BLE001
                logger.debug("EgoBlur scale pass failed: %s", exc)
                continue
            for box in found:
                mapped = BoundingBox(
                    x1=int(round(box.x1 / scale)) + ox,
                    y1=int(round(box.y1 / scale)) + oy,
                    x2=int(round(box.x2 / scale)) + ox,
                    y2=int(round(box.y2 / scale)) + oy,
                    score=box.score,
                    source="egoblur",
                )
                raw.append(_clamp_box(mapped, image.shape))
            # Strong hit on this view — no need for bumper/upscale passes
            if any(b.score >= trust for b in raw):
                break
        return raw

    def _merge_layers(self, image: np.ndarray, image_path: str | Path, ego_boxes: list[BoundingBox]) -> list[BoundingBox]:
        """Prefer EgoBlur-only when confident; extras only as a miss-recovery path."""
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        priority = _nms(
            [
                BoundingBox(b.x1, b.y1, b.x2, b.y2, score=b.score, source=b.source or "egoblur")
                for b in ego_boxes
            ],
            iou_thresh=0.3,
        )
        # Any EgoBlur hit: trust it and skip OpenCV/OCR plate layers (those are slow).
        if priority:
            trusted = [b for b in priority if b.score >= self.EGO_TRUST_SCORE] or priority
            trusted.sort(key=lambda b: b.score, reverse=True)
            return trusted[: self.MAX_BOXES]

        extras: list[BoundingBox] = []
        try:
            for box in self._fallback.detect(image_path):
                box.source = box.source or "opencv"
                extras.append(box)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OpenCV plate layer failed: %s", exc)
        try:
            # OCR plate tokens only when EgoBlur completely missed
            extras.extend(detect_ocr_plates(image))
        except Exception as exc:  # noqa: BLE001
            logger.debug("OCR plate layer failed: %s", exc)

        supplement: list[BoundingBox] = []
        for box in extras:
            box = _clamp_box(box, image.shape)
            bw, bh = box.x2 - box.x1, box.y2 - box.y1
            if bw < 20 or bh < 8:
                continue
            aspect = bw / float(max(1, bh))
            if not (1.6 <= aspect <= 6.5):
                continue
            if _looks_like_brake_light(hsv, box.x1, box.y1, bw, bh, gray):
                continue
            if not _has_character_structure(gray, box.x1, box.y1, bw, bh):
                continue
            if any(_iou(box, p) >= 0.12 for p in priority):
                continue
            cx, cy = (box.x1 + box.x2) // 2, (box.y1 + box.y2) // 2
            if any(p.x1 <= cx <= p.x2 and p.y1 <= cy <= p.y2 for p in priority):
                continue
            supplement.append(box)

        supplement = _nms(supplement, iou_thresh=0.35)
        remaining = max(0, self.MAX_BOXES - len(priority))
        supplement.sort(key=_plate_quality, reverse=True)
        return (priority + supplement[:remaining])[: self.MAX_BOXES]

    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        image = _load_bgr(image_path)
        if not self._egoblur_available():
            extras = list(self._fallback.detect(image_path))
            for b in extras:
                b.source = b.source or "opencv"
            try:
                extras.extend(detect_ocr_plates(image))
            except Exception:  # noqa: BLE001
                pass
            return _nms(extras, iou_thresh=0.35)[: self.MAX_BOXES]
        try:
            ego = self._postprocess(image, self._egoblur_multiscale(image))
            return self._merge_layers(image, image_path, ego)
        except Exception as exc:
            logger.warning("EgoBlur plate detect failed (%s); using OpenCV + OCR", exc)
            extras = list(self._fallback.detect(image_path))
            for b in extras:
                b.source = b.source or "opencv"
            try:
                extras.extend(detect_ocr_plates(image))
            except Exception:  # noqa: BLE001
                pass
            return _nms(extras, iou_thresh=0.35)[: self.MAX_BOXES]

    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        input_path, output_path = Path(input_path), Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = _load_bgr(input_path)
        boxes = self.detect(input_path)
        redacted = _blur_and_outline(image, boxes)
        cv2.imwrite(str(output_path), redacted)
        return boxes


class OpenCVPlateRedactor(PlateRedactor):
    """
    Plate detector using MSER (text regions) + colour cues.

    Used as EgoBlur supplement / fallback. Tuned for recall on yellow/white
    plates while still rejecting brake lights.
    """

    MAX_BOXES = 3
    MIN_SCORE = 2.2

    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        image = _load_bgr(image_path)
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        candidates: list[BoundingBox] = []
        candidates.extend(self._detect_mser(gray, hsv, w, h))
        candidates.extend(self._detect_colour_masks(gray, hsv, w, h))

        filtered = [b for b in candidates if b.score >= self.MIN_SCORE]
        filtered = [
            b
            for b in filtered
            if not _looks_like_brake_light(hsv, b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1, gray)
        ]
        filtered = _nms(filtered, iou_thresh=0.45)
        filtered.sort(key=lambda b: b.score, reverse=True)
        refined = [_refine_plate_box(_clamp_box(b, image.shape), gray, hsv) for b in filtered]
        return _nms(refined, iou_thresh=0.3)[: self.MAX_BOXES]

    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        input_path, output_path = Path(input_path), Path(output_path)
        image = _load_bgr(input_path)
        boxes = self.detect(input_path)
        redacted = _blur_and_outline(image, boxes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), redacted)
        return boxes

    def _append_box(
        self,
        boxes: list[BoundingBox],
        *,
        x: int,
        y: int,
        bw: int,
        bh: int,
        img_w: int,
        img_h: int,
        gray: np.ndarray,
        hsv: np.ndarray,
        base: float,
    ) -> None:
        score = _score_candidate(
            x=x, y=y, bw=bw, bh=bh, img_w=img_w, img_h=img_h, gray=gray, hsv=hsv, base=base
        )
        if score is None:
            return
        boxes.append(
            BoundingBox(x1=x, y1=y, x2=x + bw, y2=y + bh, score=score, source="opencv")
        )

    def _detect_mser(
        self, gray: np.ndarray, hsv: np.ndarray, img_w: int, img_h: int
    ) -> list[BoundingBox]:
        boxes: list[BoundingBox] = []
        mser = cv2.MSER_create()
        mser.setMinArea(50)
        mser.setMaxArea(max(500, int(img_w * img_h * 0.08)))

        yellow = cv2.inRange(hsv, (8, 35, 50), (40, 255, 255))
        sources: list[tuple[np.ndarray, float]] = [
            (gray, 0.82),
            (255 - gray, 0.8),
            (yellow, 0.86),  # washed UK yellow plates
        ]
        for src, base in sources:
            try:
                regions, _ = mser.detectRegions(src)
            except cv2.error:
                continue
            for pts in regions:
                x, y, bw, bh = cv2.boundingRect(pts)
                self._append_box(
                    boxes,
                    x=x,
                    y=y,
                    bw=bw,
                    bh=bh,
                    img_w=img_w,
                    img_h=img_h,
                    gray=gray,
                    hsv=hsv,
                    base=base,
                )
        return boxes

    def _detect_colour_masks(
        self, gray: np.ndarray, hsv: np.ndarray, img_w: int, img_h: int
    ) -> list[BoundingBox]:
        """Secondary pass: colour blobs that also contain character structure."""
        boxes: list[BoundingBox] = []
        masks = [
            (cv2.inRange(hsv, (8, 40, 60), (40, 255, 255)), 0.84),  # yellow
            (cv2.inRange(hsv, (95, 60, 45), (130, 255, 255)), 0.8),  # blue
            (cv2.inRange(hsv, (0, 0, 155), (180, 55, 255)), 0.82),  # white
            (
                cv2.bitwise_or(
                    cv2.inRange(hsv, (0, 70, 50), (12, 255, 255)),
                    cv2.inRange(hsv, (160, 70, 50), (180, 255, 255)),
                ),
                0.86,
            ),  # red EU / demo
        ]
        for mask, base in masks:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 4))
            closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, bw, bh = cv2.boundingRect(cnt)
                purity = float(np.count_nonzero(closed[y : y + bh, x : x + bw])) / float(max(1, bw * bh))
                if purity < 0.25:
                    continue
                self._append_box(
                    boxes,
                    x=x,
                    y=y,
                    bw=bw,
                    bh=bh,
                    img_w=img_w,
                    img_h=img_h,
                    gray=gray,
                    hsv=hsv,
                    base=base,
                )
        return boxes


class AnnotatedPlateRedactor(PlateRedactor):
    """Test helper: redact explicitly provided bounding boxes."""

    def __init__(self, boxes: list[BoundingBox]) -> None:
        self.boxes = boxes

    def detect(self, image_path: str | Path) -> list[BoundingBox]:
        return list(self.boxes)

    def redact(self, input_path: str | Path, output_path: str | Path) -> list[BoundingBox]:
        input_path, output_path = Path(input_path), Path(output_path)
        image = _load_bgr(input_path)
        redacted = _blur_and_outline(image, self.boxes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), redacted)
        return list(self.boxes)
