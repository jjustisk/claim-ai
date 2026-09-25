"""Unit tests for text PII detection and placeholders."""

from __future__ import annotations

from app.services.pii.detector import PIIDetector
from app.services.pii.placeholders import PlaceholderRegistry, rehydrate_text


def test_basic_pii_replacement():
    detector = PIIDetector()
    registry = PlaceholderRegistry()
    text = "John Smith lives at 12 Maple Street."
    sanitised, count = detector.sanitize_text(text, registry)
    assert count >= 1
    assert "John Smith" not in sanitised
    # Person should become CUSTOMER_*
    assert "CUSTOMER_" in sanitised or "ADDRESS_" in sanitised


def test_multiple_pii_types_structured(sample_claim, claim_service):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    session = claim_service.sanitize(session.session_id)
    claim = session.text_result.sanitised_claim
    assert claim["customer_name"].startswith("CUSTOMER_")
    assert claim["phone"].startswith("PHONE_")
    assert claim["email"].startswith("EMAIL_")
    assert "John Smith" not in claim["customer_name"]
    assert "0412" not in claim["phone"]
    assert "john@example.com" not in claim["email"]
    assert claim["claim_description"] == "Water damage to kitchen"


def test_placeholder_mapping_stored(sample_claim, claim_service, storage):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.sanitize(session.session_id)
    mapping = storage.load_mapping(session.session_id)
    assert any(v == "John Smith" for v in mapping.values())
    assert "CUSTOMER_1" in mapping
    assert mapping["CUSTOMER_1"] == "John Smith"


def test_session_isolation(claim_service, storage):
    a = claim_service.create_session()
    b = claim_service.create_session()
    claim_service.add_claim_record(a.session_id, {"customer_name": "John Smith"})
    claim_service.add_claim_record(b.session_id, {"customer_name": "Sarah Jones"})
    claim_service.sanitize(a.session_id)
    claim_service.sanitize(b.session_id)
    map_a = storage.load_mapping(a.session_id)
    map_b = storage.load_mapping(b.session_id)
    assert map_a.get("CUSTOMER_1") == "John Smith"
    assert map_b.get("CUSTOMER_1") == "Sarah Jones"
    assert map_a["CUSTOMER_1"] != map_b["CUSTOMER_1"]


def test_rehydrate_unknown_placeholder():
    text, unknown = rehydrate_text("CUSTOMER_999 submitted the claim.", {"CUSTOMER_1": "John Smith"})
    assert "CUSTOMER_999" in text
    assert "CUSTOMER_999" in unknown


def test_dates_use_date_prefix_not_dob():
    """Policy/schedule dates must be DATE_*; DOB_ is only for birth dates."""
    detector = PIIDetector()
    registry = PlaceholderRegistry()
    text = (
        "Schedule date: 26 September 2025. "
        "Policy period 01 October 2025 to 30 September 2026. "
        "POLICY SCHEDULE Contents + Personal Valuables."
    )
    sanitised, _ = detector.sanitize_text(text, registry)
    assert "DOB_" not in sanitised
    assert "SCHEDULE" in sanitised  # must not redact the word Schedule as a date
    assert "DATE_" in sanitised
    assert "01 October 2025" not in sanitised or "DATE_" in sanitised


def test_dob_context_and_structured_field(sample_claim, claim_service):
    detector = PIIDetector()
    registry = PlaceholderRegistry()
    text = "Date of birth: 12 April 1988. Policy starts 01 October 2025."
    sanitised, _ = detector.sanitize_text(text, registry)
    assert "DOB_" in sanitised
    assert "DATE_" in sanitised
    assert "12 April 1988" not in sanitised
    assert "01 October 2025" not in sanitised

    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    session = claim_service.sanitize(session.session_id)
    claim = session.text_result.sanitised_claim
    assert claim["date_of_birth"].startswith("DOB_")
