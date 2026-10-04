import os
from pydantic_settings import BaseSettings

from app.connectors.secrets import (
    VAULT_SECRET_FIELDS,
    get_key_vault_url,
    get_keyvault_secret,
    is_running_on_azure,
)
from app.security import (
    is_production,
    secrets_source,
    use_env_secrets,
    validate_cors_origins,
    validate_database_url,
    validate_jwt_secret,
)


class Settings(BaseSettings):
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    azure_storage_images_container_name: str = "claims-images"
    azure_storage_videos_container_name: str = "claims-videos"
    azure_storage_pds_policies_container_name: str = "pds-policies"
    pinecone_environment: str = ""

    chroma_host: str = ""
    chroma_port: int = 8000
    chroma_persist_directory: str = "./data/chroma"
    chroma_collection_name: str = "claim-ai"
    # Shared secret for Chroma token auth (Bearer). Required when talking to
    # a remote Chroma server that has auth enabled (Docker Compose / Azure).
    chroma_auth_token: str = ""

    database_url: str = ""
    jwt_secret_key: str = ""
    azure_storage_connection_string: str = ""
    pinecone_api_key: str = ""
    azure_communication_connection_string: str = ""
    # Verified sender identities in the ACS resource - an email domain's
    # "from" address, and a purchased/verified phone number for SMS.
    azure_communication_email_sender: str = ""
    azure_communication_sms_sender: str = ""
    # Kill switch: false skips every notification attempt entirely (no send,
    # no Notification row), without needing to blank the ACS credentials.
    notifications_enabled: bool = False

    azure_ai_project_endpoint: str = ""
    azure_ai_services_endpoint: str = ""
    foundry_gpt_deployment: str = "gpt-5.5"
    foundry_mini_deployment: str = "gpt-5.4-mini"
    foundry_nano_deployment: str = "gpt-5.4-nano"
    foundry_router_deployment: str = "model-router"
    foundry_claude_deployment: str = "model-router"
    foundry_embedding_deployment: str = "text-embedding-3-large"

    # Vue (Vite) and other local frontends. Comma-separated.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Security / deployment toggles (also readable from APP_ENV)
    enable_test_ui: bool | None = None
    enable_openapi_docs: bool | None = None

    model_config = {"env_file": "../.env", "extra": "ignore"}

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def test_ui_enabled(self) -> bool:
        if self.enable_test_ui is not None:
            return self.enable_test_ui
        return not is_production()

    def openapi_docs_enabled(self) -> bool:
        if self.enable_openapi_docs is not None:
            return self.enable_openapi_docs
        return not is_production()


FOUNDRY_VAULT_SECRET_FIELDS: dict[str, str] = {
    "azure-ai-project-endpoint": "azure_ai_project_endpoint",
    "azure-ai-services-endpoint": "azure_ai_services_endpoint",
    "foundry-gpt-deployment": "foundry_gpt_deployment",
    "foundry-mini-deployment": "foundry_mini_deployment",
    "foundry-nano-deployment": "foundry_nano_deployment",
    "foundry-router-deployment": "foundry_router_deployment",
    "foundry-claude-deployment": "foundry_claude_deployment",
}


def _vault_fields_for_mode() -> dict[str, str]:
    if os.getenv("CLAIM_AI_SETTINGS_MODE") == "foundry":
        return FOUNDRY_VAULT_SECRET_FIELDS
    return VAULT_SECRET_FIELDS


def _finalize(settings: Settings) -> Settings:
    validate_jwt_secret(settings.jwt_secret_key)
    validate_database_url(settings.database_url)
    validate_cors_origins(settings.cors_origins)
    if not settings.database_url and (
        is_production() or secrets_source() == "env"
    ):
        raise ValueError("DATABASE_URL is required.")
    return settings


def load_settings() -> Settings:
    settings = Settings()

    if os.getenv("CI") == "true" and not is_running_on_azure():
        if not settings.database_url:
            settings = settings.model_copy(
                update={"database_url": "postgresql://ci:ci@localhost/ci"}
            )
        return settings

    if (
        os.getenv("CLAIM_AI_SETTINGS_MODE") == "foundry"
        and settings.azure_ai_project_endpoint
    ):
        return settings

    # Docker / local: use process env + .env only (never bake secrets into images).
    if use_env_secrets(settings.database_url, settings.jwt_secret_key):
        return _finalize(settings)

    updates: dict[str, str] = {}
    missing: list[str] = []
    vault_fields = _vault_fields_for_mode()

    for secret_name, field_name in vault_fields.items():
        # Prefer non-empty env already loaded by pydantic; vault fills gaps / Azure prod.
        current = getattr(settings, field_name, None)
        if isinstance(current, str) and current.strip():
            continue
        value = get_keyvault_secret(secret_name)
        if value:
            updates[field_name] = value
        elif field_name == "database_url":
            missing.append(secret_name)
        elif (
            os.getenv("CLAIM_AI_SETTINGS_MODE") == "foundry"
            and field_name == "azure_ai_project_endpoint"
            and not settings.azure_ai_project_endpoint
        ):
            missing.append(secret_name)

    if missing and is_running_on_azure():
        raise ValueError(
            f"Required Key Vault secret(s) missing: {', '.join(missing)}. "
            f"Vault: {get_key_vault_url()}"
        )

    if missing and not settings.database_url and "database-url" in missing:
        raise ValueError(
            f"Required Key Vault secret(s) missing: {', '.join(missing)}. "
            f"Vault: {get_key_vault_url()}. "
            "For Docker/local, set CLAIM_AI_SECRETS_SOURCE=env and provide DATABASE_URL "
            "and JWT_SECRET_KEY in the environment."
        )

    merged = settings.model_copy(update=updates)
    return _finalize(merged)


settings = load_settings()