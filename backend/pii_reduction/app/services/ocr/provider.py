"""OCR provider abstraction."""

from __future__ import annotations

import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image: str | Path | Image.Image) -> str:
        ...

    def extract_words(self, image: str | Path | Image.Image | object) -> list[dict]:
        """Word boxes for in-image masking. Default: none."""
        return []


class TesseractOCRProvider(OCRProvider):
    def __init__(self, tesseract_cmd: str | None = None) -> None:
        import pytesseract

        self._pytesseract = pytesseract
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def available(self) -> bool:
        cmd = getattr(self._pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        return shutil.which(str(cmd)) is not None or Path(str(cmd)).exists()

    def extract_text(self, image: str | Path | Image.Image) -> str:
        if isinstance(image, (str, Path)):
            img = Image.open(image)
        else:
            try:
                import numpy as np

                if isinstance(image, np.ndarray):
                    img = Image.fromarray(cv2_to_rgb(image))
                else:
                    img = image
            except ImportError:
                img = image
        try:
            return self._pytesseract.image_to_string(img) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR failed: %s", exc)
            return ""

    def extract_words(self, image: str | Path | Image.Image | object) -> list[dict]:
        import numpy as np

        scale = 1.0
        if isinstance(image, np.ndarray):
            img, scale = _downscale_for_ocr(image)
            img = Image.fromarray(cv2_to_rgb(img))
        elif isinstance(image, (str, Path)):
            img = Image.open(image)
            img, scale = _downscale_pil_for_ocr(img)
        else:
            img = image
            if isinstance(img, Image.Image):
                img, scale = _downscale_pil_for_ocr(img)
        try:
            # OEM 1 = LSTM only; PSM 6 = block of text — faster than default sparse
            data = self._pytesseract.image_to_data(
                img,
                output_type=self._pytesseract.Output.DICT,
                config="--oem 1 --psm 6",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR word extract failed: %s", exc)
            return []
        words: list[dict] = []
        n = len(data.get("text", []))
        inv = 1.0 / scale if scale else 1.0
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = 0.0
            if conf < 25:
                continue
            words.append(
                {
                    "text": text,
                    "x": int(round(int(data["left"][i]) * inv)),
                    "y": int(round(int(data["top"][i]) * inv)),
                    "w": int(round(int(data["width"][i]) * inv)),
                    "h": int(round(int(data["height"][i]) * inv)),
                    "conf": conf,
                    "line": int(data.get("line_num", [0] * n)[i]),
                }
            )
        return words


_OCR_MAX_SIDE = 1280


def _downscale_for_ocr(image_bgr):
    import cv2

    h, w = image_bgr.shape[:2]
    long_side = max(h, w)
    if long_side <= _OCR_MAX_SIDE:
        return image_bgr, 1.0
    scale = _OCR_MAX_SIDE / float(long_side)
    view = cv2.resize(
        image_bgr,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return view, scale


def _downscale_pil_for_ocr(img: Image.Image) -> tuple[Image.Image, float]:
    w, h = img.size
    long_side = max(h, w)
    if long_side <= _OCR_MAX_SIDE:
        return img, 1.0
    scale = _OCR_MAX_SIDE / float(long_side)
    resized = img.resize(
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        Image.Resampling.BILINEAR,
    )
    return resized, scale


def cv2_to_rgb(image_bgr):
    import cv2

    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


class NoOpOCRProvider(OCRProvider):
    def extract_text(self, image: str | Path | Image.Image) -> str:
        return ""


def get_ocr_provider(backend: str = "tesseract", tesseract_cmd: str | None = None) -> OCRProvider:
    if backend == "noop":
        return NoOpOCRProvider()
    provider = TesseractOCRProvider(tesseract_cmd=tesseract_cmd)
    if not provider.available():
        logger.warning("Tesseract not available; OCR will return empty text")
    return provider
