"""Azure Key Vault access for production deployments."""

from __future__ import annotations

import os
from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient

KEY_VAULT_NAME = "claim-ai-kv"

VAULT_SECRET_FIELDS: dict[str, str] = {
    "database-url": "database_url",
    "jwt-secret-key": "jwt_secret_key",
    "azure-storage-connection-string": "azure_storage_connection_string",
    "openai-api-key": "openai_api_key",
    "anthropic-api-key": "anthropic_api_key",
    "pinecone-api-key": "pinecone_api_key",
    "azure-communication-connection-string": "azure_communication_connection_string",
}

FIELD_VAULT_SECRETS: dict[str, str] = {v: k for k, v in VAULT_SECRET_FIELDS.items()}

ENV_VAULT_SECRETS: dict[str, str] = {
    "DATABASE_URL": "database-url",
    "JWT_SECRET_KEY": "jwt-secret-key",
    "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
    "OPENAI_API_KEY": "openai-api-key",
    "ANTHROPIC_API_KEY": "anthropic-api-key",
    "PINECONE_API_KEY": "pinecone-api-key",
    "AZURE_COMMUNICATION_CONNECTION_STRING": "azure-communication-connection-string",
}

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
    if _credential is None:
        _credential = ManagedIdentityCredential()
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
