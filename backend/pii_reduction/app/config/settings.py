"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PII Reduction Service"
    api_prefix: str = "/api/v1"
    data_root: Path = Field(default=Path("data"))
    encryption_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CLAIM_AI_ENCRYPTION_KEY", "ENCRYPTION_KEY"),
        description="Fernet key (url-safe base64). Generated at runtime if unset (dev only).",
    )

    # Metadata sanitisation: exiftool | mat2 | pillow
    metadata_backend: str = "exiftool"
    exiftool_path: str = "exiftool"

    # Face / plate redaction: egoblur | opencv (egoblur uses Gen1 JIT under models/)
    redaction_backend: str = "egoblur"
    egoblur_face_model_path: str | None = "models/ego_blur_face.jit"
    egoblur_lp_model_path: str | None = "models/ego_blur_lp.jit"
    egoblur_face_score_threshold: float = 0.45
    egoblur_lp_score_threshold: float = 0.55

    # OCR: tesseract | noop
    ocr_backend: str = "tesseract"
    tesseract_cmd: str | None = None

    # Retention (hours); 0 = keep indefinitely
    retention_raw_hours: int = 24
    retention_mapping_hours: int = 72
    retention_sanitised_hours: int = 168
    retention_audit_hours: int = 8760

    # Roles → API keys (comma-separated keys per role in env)
    api_keys_pii_processor: str = "dev-processor-key"
    api_keys_pii_rehydrator: str = "dev-rehydrator-key"
    api_keys_claims_user: str = "dev-claims-key"
    api_keys_auditor: str = "dev-auditor-key"
    api_keys_admin: str = "dev-admin-key"

    # Claim schema: JSON path or inline defaults
    claim_schema_path: Path | None = None

    # Entity types treated as sensitive for Presidio + custom recognisers
    enabled_entity_types: str = (
        "PERSON,LOCATION,PHONE_NUMBER,EMAIL_ADDRESS,DATE_TIME,DOB,"
        "CREDIT_CARD,IBAN_CODE,IP_ADDRESS,"
        "AU_PHONE,AU_POSTCODE,DRIVER_LICENSE,MEDICARE,"
        "ABN,ACN,BSB,ACCOUNT_NUMBER,POLICY_NUMBER,CLAIM_NUMBER,"
        "CLAIM_AMOUNT,AU_ADDRESS"
    )

    def role_api_keys(self) -> dict[str, set[str]]:
        return {
            "PII_PROCESSOR": {k.strip() for k in self.api_keys_pii_processor.split(",") if k.strip()},
            "PII_REHYDRATOR": {k.strip() for k in self.api_keys_pii_rehydrator.split(",") if k.strip()},
            "CLAIMS_USER": {k.strip() for k in self.api_keys_claims_user.split(",") if k.strip()},
            "AUDITOR": {k.strip() for k in self.api_keys_auditor.split(",") if k.strip()},
            "ADMIN": {k.strip() for k in self.api_keys_admin.split(",") if k.strip()},
        }

    def enabled_entities(self) -> set[str]:
        return {e.strip() for e in self.enabled_entity_types.split(",") if e.strip()}

    def storage_paths(self) -> dict[str, Path]:
        root = self.data_root
        return {
            "raw": root / "raw",
            "sanitised": root / "sanitised",
            "secure_mapping": root / "secure-mapping",
            "llm_ready": root / "llm-ready",
            "audit": root / "audit",
            "sessions": root / "sessions",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


DEFAULT_CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "claim_id": {"type": "string"},
        "customer_name": {"type": "string", "pii": True, "entity": "PERSON"},
        "address": {"type": "string", "pii": True, "entity": "LOCATION"},
        "date_of_birth": {"type": "string", "pii": True, "entity": "DOB"},
        "phone": {"type": "string", "pii": True, "entity": "PHONE_NUMBER"},
        "email": {"type": "string", "pii": True, "entity": "EMAIL_ADDRESS"},
        "claim_amount": {"type": ["number", "string"], "pii": True, "entity": "CLAIM_AMOUNT"},
        "claim_description": {"type": "string"},
        "policy_number": {"type": "string", "pii": True, "entity": "POLICY_NUMBER"},
    },
}
