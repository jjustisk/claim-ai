"""Image redaction pipeline: metadata → plates → faces → OCR.

Plates run before faces so EgoBlur face (which often mis-fires on number
plates) cannot destroy the real plate and leave a bumper false-positive.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.models.session import ImageProcessingResult
from app.services.audit.logger import get_audit_logger
from app.services.image_redaction.faces import EgoBlurFaceRedactor, FaceRedactor, OpenCVFaceRedactor
from app.services.image_redaction.metadata import MetadataSanitizer, get_metadata_sanitizer
from app.services.image_redaction.plates import EgoBlurPlateRedactor, OpenCVPlateRedactor, PlateRedactor
from app.services.image_redaction.text_mask import InImageTextMasker
from app.services.ocr.provider import OCRProvider, get_ocr_provider
from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


class ImageRedactionPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        metadata: MetadataSanitizer | None = None,
        faces: FaceRedactor | None = None,
        plates: PlateRedactor | None = None,
        ocr: OCRProvider | None = None,
        pii: PIIDetector | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.metadata = metadata or get_metadata_sanitizer(
            self.settings.metadata_backend,
            self.settings.exiftool_path,
        )
        backend = (self.settings.redaction_backend or "egoblur").strip().lower()
        if faces is not None:
            self.faces = faces
        elif backend == "opencv":
            self.faces = OpenCVFaceRedactor()
        else:
            self.faces = EgoBlurFaceRedactor(
                model_path=self.settings.egoblur_face_model_path,
                score_threshold=self.settings.egoblur_face_score_threshold,
            )
        if plates is not None:
            self.plates = plates
        elif backend == "opencv":
            self.plates = OpenCVPlateRedactor()
        else:
            self.plates = EgoBlurPlateRedactor(
                model_path=self.settings.egoblur_lp_model_path,
                score_threshold=self.settings.egoblur_lp_score_threshold,
            )
        self.ocr = ocr or get_ocr_provider(self.settings.ocr_backend, self.settings.tesseract_cmd)
        self.pii = pii or PIIDetector(self.settings)
        self.audit = get_audit_logger()

    def process(
        self,
        session_id: str,
        input_id: str,
        source_path: Path,
        output_image_path: Path,
        ocr_output_path: Path,
        registry: PlaceholderRegistry,
        run_ocr: bool = True,
    ) -> tuple[ImageProcessingResult, str]:
        result = ImageProcessingResult(input_id=input_id)
        with tempfile.TemporaryDirectory(prefix="pii_reduction_img_") as tmp:
            tmp_dir = Path(tmp)
            stage = tmp_dir / "stage.jpg"

            # Stage 2.1 — metadata
            ok = self.metadata.sanitize(source_path, stage)
            result.metadata_sanitised = ok
            if ok:
                self.audit.log("EXIF_REMOVED", session_id=session_id, input_id=input_id)
            else:
                result.errors.append("metadata_sanitisation_failed")

            current = stage if stage.exists() else source_path

            # Stage 2.2 — plates FIRST (before face model can erase them)
            plate_out = tmp_dir / "plates.jpg"
            try:
                plate_boxes = self.plates.redact(current, plate_out)
                result.plates_detected = len(plate_boxes)
                result.plates_redacted = len(plate_boxes)
                if plate_boxes:
                    self.audit.log(
                        "PLATE_REDACTED",
                        session_id=session_id,
                        input_id=input_id,
                        count=len(plate_boxes),
                    )
                current = plate_out
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"plate_redaction_failed:{exc}")

            # Stage 2.3 — faces (skip plate-shaped false positives)
            face_out = tmp_dir / "faces.jpg"
            try:
                face_boxes = self.faces.redact(current, face_out)
                result.faces_detected = len(face_boxes)
                result.faces_redacted = len(face_boxes)
                if face_boxes:
                    self.audit.log(
                        "FACE_REDACTED",
                        session_id=session_id,
                        input_id=input_id,
                        count=len(face_boxes),
                    )
                current = face_out
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"face_redaction_failed:{exc}")

            # Stage 2.4 — OCR + mask remaining on-image PII (house numbers, signs, mail)
            sanitised_ocr = ""
            if run_ocr:
                masker = InImageTextMasker(self.ocr, self.pii)
                text_out = tmp_dir / "textmask.jpg"
                try:
                    text_boxes, sanitised_ocr = masker.mask_path(current, text_out, registry)
                    result.text_regions_redacted = len(text_boxes)
                    if text_boxes:
                        self.audit.log(
                            "IMAGE_TEXT_REDACTED",
                            session_id=session_id,
                            input_id=input_id,
                            count=len(text_boxes),
                        )
                    current = text_out
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"image_text_mask_failed:{exc}")
                    raw_text = self.ocr.extract_text(current)
                    sanitised_ocr, _ = self.pii.sanitize_text(raw_text, registry)

            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            current_path = Path(current)
            if current_path.exists():
                output_image_path.write_bytes(current_path.read_bytes())

            result.sanitised_path = str(output_image_path)
            self.audit.log("IMAGE_PROCESSED", session_id=session_id, input_id=input_id)

            if run_ocr:
                if not sanitised_ocr:
                    # Prefer OCR words already collected by the text masker — avoid
                    # a second full Tesseract pass on the same image.
                    raw_text = self.ocr.extract_text(
                        output_image_path if output_image_path.exists() else source_path
                    )
                    sanitised_ocr, _ = self.pii.sanitize_text(raw_text, registry)
                ocr_output_path.parent.mkdir(parents=True, exist_ok=True)
                ocr_output_path.write_text(sanitised_ocr, encoding="utf-8")
                result.ocr_completed = True
                result.ocr_path = str(ocr_output_path)
                self.audit.log("OCR_COMPLETED", session_id=session_id, input_id=input_id)

        return result, sanitised_ocr
