"""Azure Key Vault access for all environments."""

from __future__ import annotations

import os
from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

KEY_VAULT_NAME = "claim-ai-kv"

VAULT_SECRET_FIELDS: dict[str, str] = {
    "database-url": "database_url",
    "jwt-secret-key": "jwt_secret_key",
    "jwt-algorithm": "jwt_algorithm",
    "azure-storage-connection-string": "azure_storage_connection_string",
    "azure-storage-images-container-name": "azure_storage_images_container_name",
    "azure-storage-videos-container-name": "azure_storage_videos_container_name",
    "azure-storage-pds-policies-container-name": "azure_storage_pds_policies_container_name",
    "openai-api-key": "openai_api_key",
    "anthropic-api-key": "anthropic_api_key",
    "pinecone-api-key": "pinecone_api_key",
    "pinecone-environment": "pinecone_environment",
    "azure-communication-connection-string": "azure_communication_connection_string",
}

FIELD_VAULT_SECRETS: dict[str, str] = {v: k for k, v in VAULT_SECRET_FIELDS.items()}

ENV_VAULT_SECRETS: dict[str, str] = {
    "DATABASE_URL": "database-url",
    "JWT_SECRET_KEY": "jwt-secret-key",
    "JWT_ALGORITHM": "jwt-algorithm",
    "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
    "AZURE_STORAGE_IMAGES_CONTAINER_NAME": "azure-storage-images-container-name",
    "AZURE_STORAGE_VIDEOS_CONTAINER_NAME": "azure-storage-videos-container-name",
    "AZURE_STORAGE_PDS_POLICIES_CONTAINER_NAME": "azure-storage-pds-policies-container-name",
    "OPENAI_API_KEY": "openai-api-key",
    "ANTHROPIC_API_KEY": "anthropic-api-key",
    "PINECONE_API_KEY": "pinecone-api-key",
    "PINECONE_ENVIRONMENT": "pinecone-environment",
    "AZURE_COMMUNICATION_CONNECTION_STRING": "azure-communication-connection-string",
    "AZURE_KEY_VAULT_URL": "azure-key-vault-url",
    "AZURE_TENANT_ID": "azure-tenant-id",
    "AZURE_CLIENT_ID": "azure-client-id",
    "AZURE_CLIENT_SECRET": "azure-client-secret",
}


def env_var_to_secret_name(env_var: str) -> str:
    return env_var.lower().replace("_", "-")


_client: SecretClient | None = None
_credential: TokenCredential | None = None


def is_running_on_azure() -> bool:
    return any(
        os.getenv(marker)
        for marker in (
            "WEBSITE_INSTANCE_ID",
            "CONTAINER_APP_NAME",
            "AKS_SERVICE_HOST",
            "IDENTITY_ENDPOINT",
        )
    )


def get_key_vault_name() -> str:
    return KEY_VAULT_NAME


def get_key_vault_url() -> str:
    return f"https://{get_key_vault_name()}.vault.azure.net/"


def get_azure_credential() -> TokenCredential:
    global _credential
    if _credential is not None:
        return _credential

    if is_running_on_azure():
        _credential = ManagedIdentityCredential()
    else:
        _credential = AzureCliCredential()

    return _credential


def _get_client() -> SecretClient:
    global _client
    vault_url = get_key_vault_url()
    if _client is None or _client.vault_url.rstrip("/") != vault_url.rstrip("/"):
        _client = SecretClient(
            vault_url=vault_url,
            credential=get_azure_credential(),
        )
    return _client


@lru_cache(maxsize=32)
def get_keyvault_secret(secret_name: str) -> str | None:
    try:
        secret = _get_client().get_secret(secret_name)
        return secret.value
    except ResourceNotFoundError:
        return None
