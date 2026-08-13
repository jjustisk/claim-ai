import os
from pydantic_settings import BaseSettings

from app.secrets import (
    VAULT_SECRET_FIELDS,
    get_key_vault_url,
    get_keyvault_secret,
    is_running_on_azure,
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

    database_url: str = ""
    jwt_secret_key: str = ""
    azure_storage_connection_string: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    pinecone_api_key: str = ""
    azure_communication_connection_string: str = ""

    model_config = {"env_file": "../.env", "extra": "ignore"}


def load_settings() -> Settings:
    settings = Settings()

    if os.getenv("CI") == "true" and not is_running_on_azure():
        if not settings.database_url:
            settings = settings.model_copy(
                update={"database_url": "postgresql://ci:ci@localhost/ci"}
            )
        return settings

    updates: dict[str, str] = {}
    missing: list[str] = []

    for secret_name, field_name in VAULT_SECRET_FIELDS.items():
        value = get_keyvault_secret(secret_name)
        if value:
            updates[field_name] = value
        elif field_name == "database_url":
            missing.append(secret_name)

    if missing:
        raise ValueError(
            f"Required Key Vault secret(s) missing: {', '.join(missing)}. "
            f"Vault: {get_key_vault_url()}"
        )

    return settings.model_copy(update=updates)


settings = load_settings()
