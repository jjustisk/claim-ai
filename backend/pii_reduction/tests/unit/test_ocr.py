"""OCR → PII detection path."""

from __future__ import annotations

from pathlib import Path

from app.services.image_redaction.pipeline import ImageRedactionPipeline
from app.services.ocr.provider import OCRProvider
from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry


class FakeOCR(OCRProvider):
    def extract_text(self, image):
        return "John Smith\n0412 123 456"


def test_ocr_then_pii(ocr_image: Path, tmp_path: Path, settings):
    pipeline = ImageRedactionPipeline(
        settings=settings,
        ocr=FakeOCR(),
        pii=PIIDetector(settings),
    )
    registry = PlaceholderRegistry()
    out_img = tmp_path / "out.jpg"
    out_ocr = tmp_path / "out.txt"
    result, sanitised = pipeline.process(
        session_id="S1",
        input_id="IMG1",
        source_path=ocr_image,
        output_image_path=out_img,
        ocr_output_path=out_ocr,
        registry=registry,
    )
    assert result.ocr_completed
    assert "John Smith" not in sanitised
    assert "0412 123 456" not in sanitised
    assert "CUSTOMER_" in sanitised or "PHONE_" in sanitised or len(registry.mapping) >= 1
    # Structured replacement via free text should create placeholders
    assert any(v == "John Smith" for v in registry.mapping.values()) or "CUSTOMER" in sanitised
