"""Metadata sanitisation interface — ExifTool primary, MAT2/Pillow alternatives."""

from __future__ import annotations

import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class MetadataSanitizer(ABC):
    @abstractmethod
    def sanitize(self, input_path: str | Path, output_path: str | Path) -> bool:
        """Remove sensitive metadata. Returns True on success."""
        ...


class ExifToolMetadataSanitizer(MetadataSanitizer):
    _warned_missing = False

    def __init__(self, exiftool_path: str = "exiftool") -> None:
        self.exiftool_path = exiftool_path

    def available(self) -> bool:
        return shutil.which(self.exiftool_path) is not None

    def sanitize(self, input_path: str | Path, output_path: str | Path) -> bool:
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.available():
            if not ExifToolMetadataSanitizer._warned_missing:
                logger.warning(
                    "ExifTool not found; using Pillow for metadata strip "
                    "(this warning is shown once)"
                )
                ExifToolMetadataSanitizer._warned_missing = True
            return PillowMetadataSanitizer().sanitize(input_path, output_path)
        # Copy then strip all tags
        shutil.copy2(input_path, output_path)
        cmd = [
            self.exiftool_path,
            "-all=",
            "-overwrite_original",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                logger.error("ExifTool failed: %s", result.stderr)
                return PillowMetadataSanitizer().sanitize(input_path, output_path)
            return True
        except OSError as exc:
            logger.error("ExifTool execution error: %s", exc)
            return PillowMetadataSanitizer().sanitize(input_path, output_path)


class Mat2MetadataSanitizer(MetadataSanitizer):
    """MAT2-based sanitiser when `mat2` CLI is installed."""

    def sanitize(self, input_path: str | Path, output_path: str | Path) -> bool:
        input_path = Path(input_path)
        output_path = Path(output_path)
        if shutil.which("mat2") is None:
            return PillowMetadataSanitizer().sanitize(input_path, output_path)
        # mat2 writes alongside input as cleaned filename
        cmd = ["mat2", "--inplace", str(input_path)]
        # Work on a copy
        shutil.copy2(input_path, output_path)
        cmd = ["mat2", "--inplace", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return PillowMetadataSanitizer().sanitize(input_path, output_path)
        return True


class PillowMetadataSanitizer(MetadataSanitizer):
    """Always-available fallback: re-encode image without EXIF."""

    def sanitize(self, input_path: str | Path, output_path: str | Path) -> bool:
        import shutil

        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(input_path) as img:
                info = getattr(img, "info", {}) or {}
                has_exif = bool(info.get("exif"))
                fmt = (img.format or "").upper()
                # PDF page renders / clean PNGs: copy bytes, skip re-encode
                if not has_exif and fmt in {"PNG", "JPEG", "JPG"}:
                    if input_path.resolve() != output_path.resolve():
                        shutil.copy2(input_path, output_path)
                    return True
                clean = Image.new(img.mode, img.size)
                clean.paste(img)
                out_fmt = (img.format or output_path.suffix.lstrip(".") or "JPEG").upper()
                if out_fmt == "JPG":
                    out_fmt = "JPEG"
                save_kwargs = {"exif": b""} if out_fmt == "JPEG" else {}
                clean.save(output_path, format=out_fmt, **save_kwargs)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pillow metadata strip failed: %s", exc)
            try:
                shutil.copy2(input_path, output_path)
                return True
            except Exception:  # noqa: BLE001
                return False


def get_metadata_sanitizer(backend: str = "exiftool", exiftool_path: str = "exiftool") -> MetadataSanitizer:
    backend = backend.lower()
    if backend == "mat2":
        return Mat2MetadataSanitizer()
    if backend == "pillow":
        return PillowMetadataSanitizer()
    return ExifToolMetadataSanitizer(exiftool_path=exiftool_path)
