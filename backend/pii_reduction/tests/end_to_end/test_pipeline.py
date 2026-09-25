"""End-to-end Steps 1–3 without any LLM."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import claims as claims_api
from app.main import create_app
from app.models.states import ClaimState
from app.schemas.claims import RehydrationPolicy


def test_e2e_pipeline_ready_for_llm(sample_claim, claim_service, image_with_gps: Path):
    session = claim_service.create_session()
    claim_service.add_claim_record(session.session_id, sample_claim)
    claim_service.add_image(session.session_id, "damage.jpg", image_with_gps.read_bytes())
    claim_service.add_document(
        session.session_id,
        "pds.pdf",
        b"%PDF-1.4 sample pds",
        document_type="PDS",
    )

    session = claim_service.sanitize(session.session_id)
    assert session.state == ClaimState.SANITIZED
    assert session.text_result is not None
    assert session.text_result.sanitised_claim["customer_name"].startswith("CUSTOMER_")
    assert len(session.image_results) == 1
    assert session.image_results[0].metadata_sanitised

    session = claim_service.validate(session.session_id)
    assert session.state == ClaimState.VALIDATED
    assert session.validation and session.validation.passed

    session = claim_service.prepare(session.session_id)
    assert session.state == ClaimState.READY_FOR_LLM
    payload = claim_service.get_llm_payload(session.session_id)
    assert payload["status"] == "READY_FOR_LLM"
    assert "John Smith" not in str(payload)

    _, result = claim_service.rehydrate(
        session.session_id,
        {"text": "CUSTOMER_1 at ADDRESS_1"},
        policy=RehydrationPolicy.FULL,
    )
    assert "John Smith" in str(result["rehydrated"])


def test_api_flow(sample_claim, claim_service, monkeypatch):
    claims_api.set_claim_service(claim_service)
    app = create_app()
    client = TestClient(app)
    headers = {"X-API-Key": "dev-processor-key", "X-Role": "PII_PROCESSOR"}

    r = client.post("/api/v1/claims", headers=headers)
    assert r.status_code == 201
    session_id = r.json()["session_id"]
    assert session_id.startswith("CLMSESSION_")

    r = client.post(
        f"/api/v1/claims/{session_id}/inputs",
        headers=headers,
        data={"claim_json": __import__("json").dumps(sample_claim)},
    )
    assert r.status_code == 200

    r = client.post(f"/api/v1/claims/{session_id}/sanitize", headers=headers)
    assert r.status_code == 200
    assert r.json()["state"] == "SANITIZED"

    r = client.post(f"/api/v1/claims/{session_id}/validate", headers=headers)
    assert r.status_code == 200
    assert r.json()["state"] == "VALIDATED"

    r = client.post(f"/api/v1/claims/{session_id}/prepare", headers=headers)
    assert r.status_code == 200
    assert r.json()["state"] == "READY_FOR_LLM"

    r = client.get(f"/api/v1/claims/{session_id}/llm-payload", headers=headers)
    assert r.status_code == 200
    assert "John Smith" not in r.text

    # Rehydration denied for processor role
    r = client.post(
        f"/api/v1/claims/{session_id}/rehydrate",
        headers=headers,
        json={"content": "CUSTOMER_1", "rehydration_policy": "FULL"},
    )
    assert r.status_code == 403

    rehydrate_headers = {"X-API-Key": "dev-rehydrator-key", "X-Role": "PII_REHYDRATOR"}
    r = client.post(
        f"/api/v1/claims/{session_id}/rehydrate",
        headers=rehydrate_headers,
        json={"content": "CUSTOMER_1 submitted the claim.", "rehydration_policy": "FULL"},
    )
    assert r.status_code == 200
    assert r.json()["rehydrated"] == "John Smith submitted the claim."
