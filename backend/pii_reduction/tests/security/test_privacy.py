"""Security tests — LLM payload must not contain raw PII; no LLM deps."""

from __future__ import annotations

import importlib
import json
import sys

from app.models.states import ClaimState


def test_llm_payload_contains_no_raw_pii(sample_claim, claim_service):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.sanitize(session.session_id)
    claim_service.validate(session.session_id)
    session = claim_service.prepare(session.session_id)
    assert session.state == ClaimState.READY_FOR_LLM
    payload = claim_service.get_llm_payload(session.session_id)
    blob = json.dumps(payload)
    for banned in ["John Smith", "12 Maple Street", "0412 123 456", "john@example.com", "1988-04-12", "12450"]:
        assert banned not in blob
    claim = payload["claim"]
    assert claim["customer_name"].startswith("CUSTOMER_")
    assert claim["address"].startswith("ADDRESS_")
    assert claim["phone"].startswith("PHONE_")
    assert str(claim["claim_amount"]).startswith("AMOUNT_")


def test_mapping_not_in_llm_ready(sample_claim, claim_service, storage):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.sanitize(session.session_id)
    claim_service.validate(session.session_id)
    claim_service.prepare(session.session_id)
    llm_dir = storage.llm_ready_dir(session.session_id)
    assert not list(llm_dir.rglob("mapping*"))
    # Mapping exists only in secure-mapping
    assert (storage.mapping_dir(session.session_id) / "mapping.enc").exists()


def test_no_llm_libraries_required():
    """Critical architectural boundary: service must not depend on LLM stacks."""
    banned = {
        "openai",
        "anthropic",
        "transformers",
        "llama_cpp",
        "litellm",
        "langchain",
        "google.generativeai",
        "vertexai",
    }
    # Ensure none are imported by our app package modules that are already loaded
    loaded = {name.split(".")[0] for name in sys.modules}
    for name in banned:
        assert name not in loaded, f"LLM library unexpectedly loaded: {name}"
    # Import app.main fresh check of requirements file later; runtime import must succeed
    importlib.import_module("app.main")
    loaded_after = {name.split(".")[0] for name in sys.modules}
    for name in banned:
        assert name not in loaded_after


def test_rehydration_requires_session_mapping(sample_claim, claim_service):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.sanitize(session.session_id)
    claim_service.validate(session.session_id)
    claim_service.prepare(session.session_id)
    session, result = claim_service.rehydrate(
        session.session_id,
        "CUSTOMER_1 submitted the claim.",
    )
    assert result["status"] == "REHYDRATED"
    assert result["rehydrated"] == "John Smith submitted the claim."


def test_unknown_token_warning(sample_claim, claim_service):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.sanitize(session.session_id)
    claim_service.validate(session.session_id)
    claim_service.prepare(session.session_id)
    _, result = claim_service.rehydrate(
        session.session_id,
        "CUSTOMER_999 submitted the claim.",
    )
    assert result["status"] == "REHYDRATION_WARNING"
    assert "CUSTOMER_999" in result["unknown_placeholders"]
