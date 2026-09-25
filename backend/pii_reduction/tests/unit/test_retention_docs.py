"""Retention / TTL and document sanitisation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.states import ClaimState
from app.services.retention.service import MappingExpiredError, RetentionService


def test_document_text_is_sanitised_not_copied_raw(claim_service, storage):
    session = claim_service.create_session()
    claim_service.add_claim_record(
        session.session_id,
        {"customer_name": "John Smith", "claim_description": "leak"},
    )
    claim_service.add_document(
        session.session_id,
        "note.txt",
        b"Customer John Smith of 12 Maple Street called about the claim.",
        document_type="NOTE",
        content_type="text/plain",
    )
    session = claim_service.sanitize(session.session_id)
    docs_dir = storage.sanitised_dir(session.session_id) / "documents"
    pdfs = list(docs_dir.glob("*.sanitised.pdf"))
    txts = list(docs_dir.glob("*.sanitised.txt"))
    assert pdfs, "Expected redacted PDF artefact"
    assert txts, "Expected text sidecar"
    text = txts[0].read_text(encoding="utf-8")
    assert "John Smith" not in text
    assert "12 Maple Street" not in text
    assert "CUSTOMER_" in text or "ADDRESS_" in text
    pdf_bytes = pdfs[0].read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert b"John Smith" not in pdf_bytes


def test_pdf_upload_produces_redacted_pdf(claim_service, storage):
    from app.services.documents.sanitizer import build_redacted_pdf

    # Build a tiny source PDF containing PII text, then sanitise it
    raw_pdf = build_redacted_pdf(
        "Customer John Smith of 12 Maple Street called about the claim.",
        title="source",
    )
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, {"customer_name": "Jane Doe"})
    claim_service.add_document(
        session.session_id,
        "letter.pdf",
        raw_pdf,
        document_type="LETTER",
        content_type="application/pdf",
    )
    session = claim_service.sanitize(session.session_id)
    pdfs = list((storage.sanitised_dir(session.session_id) / "documents").glob("*.sanitised.pdf"))
    assert pdfs, "Expected redacted PDF"
    assert pdfs[0].read_bytes().startswith(b"%PDF")
    # Original must not be copied into sanitised/
    assert not any(p.name == "letter.pdf" for p in (storage.sanitised_dir(session.session_id) / "documents").iterdir())
    doc_inp = next(i for i in session.inputs if i.kind.value == "document")
    # Text-only PDF: digital text redaction, no EgoBlur page renders
    assert doc_inp.metadata.get("image_pages_redacted", 0) == 0
    assert doc_inp.metadata.get("text_pages_redacted", 0) >= 1


def test_photo_pdf_pages_are_image_redacted(claim_service, storage, tmp_path):
    """Scanned/photo PDF (embedded image, little/no text) still gets page image redaction."""
    import fitz
    from PIL import Image, ImageDraw

    # Build a 1-page PDF that is mostly an image with a faux plate + address text
    img = Image.new("RGB", (640, 400), color=(70, 80, 90))
    draw = ImageDraw.Draw(img)
    draw.rectangle((220, 280, 420, 330), fill=(255, 210, 0), outline=(20, 20, 20), width=2)
    draw.text((240, 295), "AB12 CDE", fill=(10, 10, 10))
    draw.text((40, 40), "12 Maple Street", fill=(255, 255, 255))
    img_path = tmp_path / "scan.png"
    img.save(img_path, "PNG")

    doc = fitz.open()
    page = doc.new_page(width=640, height=400)
    page.insert_image(page.rect, filename=str(img_path))
    pdf_bytes = doc.tobytes()
    doc.close()

    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, {"customer_name": "Jane Doe"})
    claim_service.add_document(
        session.session_id,
        "scan.pdf",
        pdf_bytes,
        document_type="PHOTO_PDF",
        content_type="application/pdf",
    )
    session = claim_service.sanitize(session.session_id)
    docs = storage.sanitised_dir(session.session_id) / "documents"
    out = list(docs.glob("*.sanitised.pdf"))
    assert out, "Expected image-redacted PDF (not withheld)"
    assert out[0].read_bytes().startswith(b"%PDF")
    doc_inp = next(i for i in session.inputs if i.kind.value == "document")
    assert doc_inp.metadata.get("image_pages_redacted") == 1
    assert not list(docs.glob("*.withheld.pdf"))


def test_hybrid_pdf_text_page_and_photo_page(claim_service, storage, tmp_path):
    """Contract text page stays on text path; photo page gets visual redaction."""
    import fitz
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 400), color=(70, 80, 90))
    draw = ImageDraw.Draw(img)
    draw.rectangle((220, 280, 420, 330), fill=(255, 210, 0), outline=(20, 20, 20), width=2)
    draw.text((240, 295), "AB12 CDE", fill=(10, 10, 10))
    img_path = tmp_path / "car.png"
    img.save(img_path, "PNG")

    doc = fitz.open()
    text_page = doc.new_page(width=595, height=842)
    text_page.insert_text(
        (50, 100),
        "Policy holder John Smith of 12 Maple Street.",
        fontsize=12,
    )
    photo_page = doc.new_page(width=640, height=400)
    photo_page.insert_image(photo_page.rect, filename=str(img_path))
    pdf_bytes = doc.tobytes()
    doc.close()

    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, {"customer_name": "Jane Doe"})
    claim_service.add_document(
        session.session_id,
        "claim_pack.pdf",
        pdf_bytes,
        document_type="PACK",
        content_type="application/pdf",
    )
    session = claim_service.sanitize(session.session_id)
    docs = storage.sanitised_dir(session.session_id) / "documents"
    out = list(docs.glob("claim_pack.sanitised.pdf"))
    assert out, "Expected hybrid sanitised PDF"
    txts = list(docs.glob("claim_pack.sanitised.txt"))
    assert txts
    text = txts[0].read_text(encoding="utf-8")
    assert "John Smith" not in text
    assert "12 Maple Street" not in text
    doc_inp = next(i for i in session.inputs if i.kind.value == "document")
    assert doc_inp.metadata.get("image_pages_redacted") == 1
    assert doc_inp.metadata.get("text_pages_redacted") == 1


def test_mapping_ttl_blocks_rehydrate(claim_service, storage, settings, monkeypatch):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, {"customer_name": "John Smith"})
    claim_service.sanitize(session.session_id)
    claim_service.validate(session.session_id)
    claim_service.prepare(session.session_id)

    mapping_path = storage.mapping_dir(session.session_id) / "mapping.enc"
    old = datetime.now(timezone.utc) - timedelta(hours=settings.retention_mapping_hours + 1)
    # Age the mapping file beyond TTL
    import os

    ts = old.timestamp()
    os.utime(mapping_path, (ts, ts))

    with pytest.raises(MappingExpiredError):
        claim_service.rehydrate(session.session_id, "CUSTOMER_1")


def test_retention_sweep_removes_expired_raw(settings, storage, tmp_path):
    settings.retention_raw_hours = 1
    settings.retention_mapping_hours = 0
    settings.retention_sanitised_hours = 0
    sid = "CLMSESSION_TESTRETENTION01"
    raw = storage.raw_dir(sid)
    raw.mkdir(parents=True, exist_ok=True)
    f = raw / "images" / "x.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"enc")
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    import os

    ts = old.timestamp()
    os.utime(f, (ts, ts))
    os.utime(raw, (ts, ts))
    counts = RetentionService(settings, storage).sweep()
    assert counts["raw"] >= 1
    assert not raw.exists()
