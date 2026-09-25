"""In-process EgoBlur Gen1 TorchScript inference (Windows-safe; no VRS).

Meta's `pip install egoblur` pulls `vrs`, which fails to build on Windows.
We install the egoblur package with `--no-deps` (or use this module alone) and
run Gen1 JIT models via torch — same path as `egoblur-gen1` / demo_ego_blur_gen1.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from app.services.image_redaction.faces import BoundingBox

logger = logging.getLogger(__name__)

_DEFAULT_NMS_IOU = 0.3
_DEFAULT_SCALE = 1.05
# Detect on a long-side cap — full-res claim photos are rarely needed for EgoBlur
_DETECT_MAX_SIDE = 1280


def resolve_model_path(configured: str | None, *candidates: str) -> Path | None:
    """Resolve an absolute/relative model path, trying local defaults."""
    paths: list[Path] = []
    if configured:
        paths.append(Path(configured))
        # Relative to pii_reduction package root (…/pii_reduction/models/…)
        pkg_root = Path(__file__).resolve().parents[3]
        paths.append(pkg_root / configured)
    pkg_root = Path(__file__).resolve().parents[3]
    for name in candidates:
        paths.append(Path("models") / name)
        paths.append(pkg_root / "models" / name)
        paths.append(Path.cwd() / "models" / name)
        paths.append(Path.cwd() / "pii_reduction" / "models" / name)
    for path in paths:
        if path.is_file():
            return path.resolve()
    return None


@lru_cache(maxsize=1)
def _device() -> str:
    try:
        import torch

        # Cap intra-op threads so multi-pass EgoBlur doesn't thrash on CPU
        try:
            import os

            n = max(1, min(4, (os.cpu_count() or 4) // 2))
            torch.set_num_threads(n)
        except Exception:  # noqa: BLE001
            pass
        return f"cuda:{torch.cuda.current_device()}" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _prepare_for_detect(image_bgr: np.ndarray, max_side: int = _DETECT_MAX_SIDE) -> tuple[np.ndarray, float]:
    """Downscale large frames for faster TorchScript inference. Returns (view, scale)."""
    h, w = image_bgr.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side:
        return image_bgr, 1.0
    scale = max_side / float(long_side)
    view = cv2.resize(
        image_bgr,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return view, scale


@lru_cache(maxsize=4)
def _load_detector(model_path: str):
    import torch
    import torchvision  # noqa: F401 — registers torchvision::nms for JIT models

    detector = torch.jit.load(model_path, map_location="cpu").to(_device())
    detector.eval()
    return detector


def egoblur_runtime_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401

        return True
    except ImportError:
        return False


def model_ready(model_path: str | None) -> bool:
    return bool(model_path) and Path(model_path).is_file() and egoblur_runtime_available()


def _image_tensor(bgr: np.ndarray):
    import torch

    chw = np.transpose(bgr, (2, 0, 1))
    return torch.from_numpy(chw).to(_device())


def _detections(
    detector,
    image_tensor,
    score_threshold: float,
    nms_iou_threshold: float = _DEFAULT_NMS_IOU,
) -> list[tuple[int, int, int, int, float]]:
    import torch
    import torchvision

    with torch.no_grad():
        boxes, _, scores, _ = detector(image_tensor)

    if boxes is None or len(boxes) == 0:
        return []

    keep = torchvision.ops.nms(boxes, scores, nms_iou_threshold)
    boxes = boxes[keep]
    scores = scores[keep]

    boxes_np = boxes.cpu().numpy()
    scores_np = scores.cpu().numpy()
    out: list[tuple[int, int, int, int, float]] = []
    for box, score in zip(boxes_np, scores_np, strict=False):
        if float(score) <= score_threshold:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
        out.append((x1, y1, x2, y2, float(score)))
    return out


def _scale_box(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    max_w: int,
    max_h: int,
    scale: float,
) -> tuple[int, int, int, int]:
    if scale == 1.0:
        return (
            max(0, x1),
            max(0, y1),
            min(max_w, x2),
            min(max_h, y2),
        )
    w, h = x2 - x1, y2 - y1
    xc, yc = x1 + w / 2, y1 + h / 2
    w, h = scale * w, scale * h
    return (
        max(0, int(xc - w / 2)),
        max(0, int(yc - h / 2)),
        min(max_w, int(xc + w / 2)),
        min(max_h, int(yc + h / 2)),
    )


def detect_boxes(
    image_bgr: np.ndarray,
    model_path: str,
    score_threshold: float,
    *,
    nms_iou_threshold: float = _DEFAULT_NMS_IOU,
    max_side: int = _DETECT_MAX_SIDE,
) -> list[BoundingBox]:
    from app.services.image_redaction.faces import BoundingBox

    detector = _load_detector(str(Path(model_path).resolve()))
    view, scale = _prepare_for_detect(image_bgr, max_side=max_side)
    tensor = _image_tensor(view)
    raw = _detections(detector, tensor, score_threshold, nms_iou_threshold)
    if scale == 1.0:
        return [BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2, score=score) for x1, y1, x2, y2, score in raw]
    inv = 1.0 / scale
    return [
        BoundingBox(
            x1=int(round(x1 * inv)),
            y1=int(round(y1 * inv)),
            x2=int(round(x2 * inv)),
            y2=int(round(y2 * inv)),
            score=score,
        )
        for x1, y1, x2, y2, score in raw
    ]


def elliptical_blur(
    image_bgr: np.ndarray,
    boxes: list[BoundingBox],
    *,
    scale: float = _DEFAULT_SCALE,
) -> np.ndarray:
    """EgoBlur-style elliptical region blur (from Gen1 visualize())."""
    image = image_bgr.copy()
    image_fg = image.copy()
    mask = np.zeros((image.shape[0], image.shape[1], 1), dtype=np.uint8)
    h, w = image.shape[:2]
    ksize = (max(1, h // 2) | 1, max(1, w // 2) | 1)

    for box in boxes:
        x1, y1, x2, y2 = _scale_box(box.x1, box.y1, box.x2, box.y2, w, h, scale)
        if x2 <= x1 or y2 <= y1:
            continue
        image_fg[y1:y2, x1:x2] = cv2.blur(image_fg[y1:y2, x1:x2], ksize)
        bw, bh = x2 - x1, y2 - y1
        cv2.ellipse(mask, (((x1 + x2) // 2, (y1 + y2) // 2), (bw, bh), 0), 255, -1)

    inverse = cv2.bitwise_not(mask)
    bg = cv2.bitwise_and(image, image, mask=inverse)
    fg = cv2.bitwise_and(image_fg, image_fg, mask=mask)
    return cv2.add(bg, fg)
