"""Extract text from uploaded documents and emit redacted PDF/text artefacts.

PDFs are handled page-by-page (hybrid):
  - Digital text on a page → Presidio + in-place PDF text redaction (fast).
  - Significant photo/scan on a page → EgoBlur faces/plates + OCR text mask.
  - A page can get both (contract text + a photo of the car/property).
Tiny logos/headers do not trigger the expensive visual path.
"""

from __future__ import annotations

import io
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry

if TYPE_CHECKING:
    from app.services.image_redaction.pipeline import ImageRedactionPipeline

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json"}
PDF_EXTENSIONS = {".pdf"}

# Render scale ≈ 108 DPI (1.5× 72). Was 2.0 — big cost for EgoBlur+OCR on photo pages.
_PDF_RENDER_SCALE = 1.5
# Image must cover at least this fraction of the page to count as a "photo"
# (filters out logos / icons / letterheads).
_MIN_PHOTO_PAGE_FRACTION = 0.12
# Single image this large always counts, even if text-heavy page.
_MIN_SINGLE_IMAGE_FRACTION = 0.08
# Almost no digital text → treat as scan/photo even with smaller images.
_SCAN_TEXT_CHAR_LIMIT = 40


def build_redacted_pdf(text: str, title: str = "Sanitised document") -> bytes:
    """Build a simple multi-page PDF containing redacted plain text (no external fonts)."""

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    raw_lines: list[str] = []
    for paragraph in (text or "").replace("\r\n", "\n").split("\n"):
        paragraph = paragraph.strip() or " "
        while len(paragraph) > 90:
            split_at = paragraph.rfind(" ", 0, 90)
            if split_at < 40:
                split_at = 90
            raw_lines.append(paragraph[:split_at])
            paragraph = paragraph[split_at:].lstrip()
        raw_lines.append(paragraph)

    lines_per_page = 48
    pages: list[list[str]] = []
    for i in range(0, max(1, len(raw_lines)), lines_per_page):
        pages.append(raw_lines[i : i + lines_per_page])

    objects: list[bytes] = []

    def add_obj(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_obj_index = add_obj(b"")

    page_ids: list[int] = []
    for page_lines in pages:
        content_parts = ["BT /F1 10 Tf 50 780 Td 14 TL"]
        first = True
        for line in page_lines:
            prefix = "T*" if not first else ""
            first = False
            content_parts.append(f"{prefix} ({_esc(line)}) Tj")
        stream = "\n".join(content_parts) + "\nET"
        stream_bytes = stream.encode("latin-1", errors="replace")
        content_id = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        page_id = add_obj(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {len(objects) + 2} 0 R >> >> >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)
        font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_obj_index - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"
    ).encode("ascii")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))
    out.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info << "
            f"/Title ({_esc(title)}) >> >>\nstartxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1", errors="replace")
    )
    return out.getvalue()


def _page_photo_coverage(page: Any) -> float:
    """Return fraction of page area covered by non-trivial embedded images."""
    page_area = abs(float(page.rect.width * page.rect.height)) or 1.0
    covered = 0.0
    try:
        xrefs = {img[0] for img in page.get_images(full=True)}
    except Exception:  # noqa: BLE001
        return 0.0
    for xref in xrefs:
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # noqa: BLE001
            continue
        for rect in rects:
            frac = abs(float(rect.width * rect.height)) / page_area
            if frac >= _MIN_SINGLE_IMAGE_FRACTION:
                covered += frac
    return min(covered, 1.0)


def page_needs_visual_redaction(page: Any, page_text: str | None = None) -> bool:
    """True when this page has significant photo/scan content (not just a logo)."""
    text = (page_text if page_text is not None else (page.get_text() or "")).strip()
    coverage = _page_photo_coverage(page)
    if coverage >= _MIN_PHOTO_PAGE_FRACTION:
        return True
    # Scanned / photo PDF page: little selectable text
    if len(text) < _SCAN_TEXT_CHAR_LIMIT and coverage >= _MIN_SINGLE_IMAGE_FRACTION:
        return True
    if len(text) < _SCAN_TEXT_CHAR_LIMIT and coverage == 0.0:
        # Full-page scan sometimes still reports an image; if not, low text alone
        # is enough to prefer visual (OCR) over empty text redaction.
        return len(text) == 0
    return False


class DocumentSanitizer:
    def __init__(
        self,
        pii: PIIDetector | None = None,
        image_pipeline: ImageRedactionPipeline | None = None,
    ) -> None:
        self.pii = pii or PIIDetector()
        self.image_pipeline = image_pipeline

    def extract_text(self, filename: str, data: bytes) -> str | None:
        ext = Path(filename).suffix.lower()
        if ext in TEXT_EXTENSIONS:
            return self._decode_text(data, ext)
        if ext in PDF_EXTENSIONS:
            return self._extract_pdf(data)
        return None

    def sanitize(
        self,
        filename: str,
        data: bytes,
        registry: PlaceholderRegistry,
        schema_pii_fields: dict[str, str] | None = None,
        *,
        session_id: str = "doc",
        input_id: str = "DOC",
        image_pipeline: ImageRedactionPipeline | None = None,
    ) -> dict[str, Any]:
        """Produce sanitised artefacts for a document."""
        ext = Path(filename).suffix.lower()
        stem = Path(filename).stem
        safe_stem = re.sub(r"[^\w.\-]+", "_", stem)[:80] or "document"
        text = self.extract_text(filename, data)
        entities = 0
        extra_files: list[dict[str, Any]] = []
        pipeline = image_pipeline or self.image_pipeline

        if ext == ".json" and text is not None:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                sanitised_obj, entities = self.pii.sanitize_claim_record(
                    payload, registry, schema_pii_fields
                )
                sanitised_text = json.dumps(sanitised_obj, indent=2)
                pdf_bytes = build_redacted_pdf(sanitised_text, title=f"{safe_stem} (sanitised)")
                extra_files.append(
                    {
                        "filename": f"{safe_stem}.sanitised.json",
                        "bytes": sanitised_text.encode("utf-8"),
                    }
                )
                return {
                    "sanitised_text": sanitised_text,
                    "sanitised_bytes": pdf_bytes,
                    "sanitised_filename": f"{safe_stem}.sanitised.pdf",
                    "extra_files": extra_files,
                    "entities": entities,
                    "binary_withheld": True,
                    "image_pages_redacted": 0,
                }

        if ext in PDF_EXTENSIONS:
            result = self._sanitize_pdf_hybrid(
                data,
                registry,
                pipeline,
                session_id=session_id,
                input_id=input_id,
                filename=filename,
            )
            if result is not None:
                sanitised_text = result["sanitised_text"]
                entities = int(result["entities"])
                # Prefer full-document Presidio text when extractable (LLM sidecar)
                if text:
                    sidecar, text_ents = self.pii.sanitize_text(text, registry)
                    sanitised_text = sidecar
                    entities = max(entities, text_ents)
                    if result.get("ocr_text"):
                        sanitised_text = (
                            f"{sanitised_text}\n\n--- page OCR ---\n{result['ocr_text']}"
                        )
                elif result.get("ocr_text"):
                    sanitised_text = result["ocr_text"]
                    entities = max(entities, sanitised_text.count("_"))

                if sanitised_text:
                    extra_files.append(
                        {
                            "filename": f"{safe_stem}.sanitised.txt",
                            "bytes": sanitised_text.encode("utf-8"),
                        }
                    )
                return {
                    "sanitised_text": sanitised_text
                    or f"[PDF sanitised: {result['page_count']} page(s)]",
                    "sanitised_bytes": result["pdf_bytes"],
                    "sanitised_filename": f"{safe_stem}.sanitised.pdf",
                    "extra_files": extra_files,
                    "entities": entities,
                    "binary_withheld": True,
                    "image_pages_redacted": result["image_pages_redacted"],
                    "text_pages_redacted": result["text_pages_redacted"],
                    "remove_filenames": [f"{safe_stem}.withheld.pdf"],
                }
            logger.warning("Hybrid PDF sanitisation failed for %s; falling back", filename)

        if text is not None:
            sanitised_text, entities = self.pii.sanitize_text(text, registry)
            pdf_bytes = build_redacted_pdf(sanitised_text, title=f"{safe_stem} (sanitised)")
            extra_files.append(
                {
                    "filename": f"{safe_stem}.sanitised.txt",
                    "bytes": sanitised_text.encode("utf-8"),
                }
            )
            return {
                "sanitised_text": sanitised_text,
                "sanitised_bytes": pdf_bytes,
                "sanitised_filename": f"{safe_stem}.sanitised.pdf",
                "extra_files": extra_files,
                "entities": entities,
                "binary_withheld": True,
                "image_pages_redacted": 0,
            }

        notice = (
            f"[DOCUMENT_WITHHELD] Original binary '{filename}' retained encrypted in raw/ only. "
            "Text could not be extracted and PDF page image redaction was unavailable "
            "(install pymupdf in the same Python env as uvicorn: pip install pymupdf)."
        )
        pdf_bytes = build_redacted_pdf(notice, title=f"{safe_stem} (withheld)")
        return {
            "sanitised_text": notice,
            "sanitised_bytes": pdf_bytes,
            "sanitised_filename": f"{safe_stem}.withheld.pdf",
            "extra_files": [],
            "entities": 0,
            "binary_withheld": True,
            "image_pages_redacted": 0,
        }

    def _sanitize_pdf_hybrid(
        self,
        data: bytes,
        registry: PlaceholderRegistry,
        pipeline: ImageRedactionPipeline | None,
        *,
        session_id: str,
        input_id: str,
        filename: str,
    ) -> dict[str, Any] | None:
        """Per-page: text redaction always when possible; visual only for photo pages."""
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz  # type: ignore
            except ImportError:
                logger.error("pymupdf not installed — cannot sanitise PDF layout")
                return None

        try:
            src = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open PDF: %s", exc)
            return None

        if src.page_count == 0:
            src.close()
            return None

        out_doc = fitz.open()
        ocr_chunks: list[str] = []
        image_pages = 0
        text_pages = 0
        entity_hits = 0

        try:
            with tempfile.TemporaryDirectory(prefix="pii_reduction_pdf_") as tmp:
                tmp_dir = Path(tmp)
                for page_index in range(src.page_count):
                    page = src.load_page(page_index)
                    page_text = page.get_text() or ""
                    needs_visual = page_needs_visual_redaction(page, page_text)

                    # 1) Digital text PII → in-place redaction (keeps layout)
                    entity_hits += self._redact_page_digital_text(page, registry)

                    if needs_visual:
                        if pipeline is None:
                            logger.warning(
                                "Page %s/%s looks like a photo but no image pipeline — "
                                "keeping text-redacted page only",
                                page_index + 1,
                                src.page_count,
                            )
                            out_doc.insert_pdf(src, from_page=page_index, to_page=page_index)
                            text_pages += 1
                            continue

                        logger.info(
                            "PDF %s page %s/%s: visual redaction (photo/scan)",
                            filename,
                            page_index + 1,
                            src.page_count,
                        )
                        page_rect = page.rect
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(_PDF_RENDER_SCALE, _PDF_RENDER_SCALE),
                            alpha=False,
                        )
                        src_path = tmp_dir / f"page_{page_index:04d}.png"
                        out_path = tmp_dir / f"page_{page_index:04d}_redacted.png"
                        ocr_path = tmp_dir / f"page_{page_index:04d}.txt"
                        pix.save(str(src_path))
                        result, ocr_text = pipeline.process(
                            session_id=session_id,
                            input_id=f"{input_id}_p{page_index}",
                            source_path=src_path,
                            output_image_path=out_path,
                            ocr_output_path=ocr_path,
                            registry=registry,
                            run_ocr=True,
                        )
                        if ocr_text:
                            ocr_chunks.append(ocr_text)
                        img_path = out_path if out_path.exists() else src_path
                        if not out_path.exists():
                            logger.warning(
                                "PDF page %s visual redaction incomplete (%s)",
                                page_index,
                                result.errors,
                            )
                        new_page = out_doc.new_page(
                            width=page_rect.width, height=page_rect.height
                        )
                        new_page.insert_image(new_page.rect, filename=str(img_path))
                        image_pages += 1
                    else:
                        logger.info(
                            "PDF %s page %s/%s: text redaction only",
                            filename,
                            page_index + 1,
                            src.page_count,
                        )
                        out_doc.insert_pdf(src, from_page=page_index, to_page=page_index)
                        text_pages += 1

            if out_doc.page_count == 0:
                return None
            pdf_bytes = out_doc.tobytes(deflate=True, garbage=3)
            return {
                "pdf_bytes": pdf_bytes,
                "ocr_text": "\n".join(ocr_chunks).strip(),
                "page_count": src.page_count,
                "image_pages_redacted": image_pages,
                "text_pages_redacted": text_pages,
                "entities": entity_hits,
                "sanitised_text": "",
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Hybrid PDF sanitisation failed: %s", exc)
            return None
        finally:
            out_doc.close()
            src.close()

    def _redact_page_digital_text(self, page: Any, registry: PlaceholderRegistry) -> int:
        """Presidio on selectable page text; burn placeholders via PDF redaction annots."""
        page_text = page.get_text() or ""
        if not page_text.strip():
            return 0
        detections = self.pii.detect(page_text)
        if not detections:
            return 0
        applied = 0
        # Longer spans first so search_for hits full names before substrings
        for det in sorted(detections, key=lambda d: len(d["text"]), reverse=True):
            raw = (det.get("text") or "").strip()
            if len(raw) < 2:
                continue
            placeholder = registry.placeholder_for(det["entity_type"], raw)
            try:
                hits = page.search_for(raw)
            except Exception:  # noqa: BLE001
                hits = []
            for rect in hits:
                try:
                    page.add_redact_annot(
                        rect,
                        text=placeholder,
                        fill=(0.92, 0.92, 0.92),
                        text_color=(0, 0, 0),
                    )
                    applied += 1
                except Exception:  # noqa: BLE001
                    continue
        if applied:
            try:
                page.apply_redactions(images=0)  # don't wipe images during text pass
            except TypeError:
                page.apply_redactions()
            except Exception as exc:  # noqa: BLE001
                logger.warning("apply_redactions failed: %s", exc)
                return 0
        return applied

    def _decode_text(self, data: bytes, ext: str) -> str:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _extract_pdf(self, data: bytes) -> str | None:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            logger.error(
                "pypdf is not installed in this environment — cannot extract PDF text. "
                "Run: pip install pypdf"
            )
            return None
        try:
            reader = PdfReader(io.BytesIO(data))
            parts: list[str] = []
            for page in reader.pages:
                try:
                    page_text = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    page_text = ""
                if not page_text.strip():
                    try:
                        page_text = page.extract_text(extraction_mode="layout") or ""
                    except Exception:  # noqa: BLE001
                        page_text = ""
                parts.append(page_text)
            text = "\n".join(parts).strip()
            if not text:
                logger.warning(
                    "PDF had %s page(s) but no extractable text (likely scanned)",
                    len(reader.pages),
                )
                return None
            return text
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF extract failed: %s", exc)
            return None
