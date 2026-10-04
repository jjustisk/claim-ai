"""Azure Key Vault access for all environments."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError
from azure.identity import (
    AzureCliCredential,
    ClientSecretCredential,
    ManagedIdentityCredential,
)
from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)

DEFAULT_KEY_VAULT_NAME = "claim-ai-kv"

VAULT_SECRET_FIELDS: dict[str, str] = {
    "database-url": "database_url",
    "jwt-secret-key": "jwt_secret_key",
    "jwt-algorithm": "jwt_algorithm",
    "azure-storage-connection-string": "azure_storage_connection_string",
    "azure-storage-images-container-name": "azure_storage_images_container_name",
    "azure-storage-videos-container-name": "azure_storage_videos_container_name",
    "azure-storage-pds-policies-container-name": "azure_storage_pds_policies_container_name",
    "pinecone-api-key": "pinecone_api_key",
    "pinecone-environment": "pinecone_environment",
    "azure-communication-connection-string": "azure_communication_connection_string",
    "azure-communication-email-sender": "azure_communication_email_sender",
    "azure-communication-sms-sender": "azure_communication_sms_sender",
    "azure-ai-project-endpoint": "azure_ai_project_endpoint",
    "azure-ai-services-endpoint": "azure_ai_services_endpoint",
    "foundry-gpt-deployment": "foundry_gpt_deployment",
    "foundry-router-deployment": "foundry_router_deployment",
    "foundry-claude-deployment": "foundry_claude_deployment",
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
    "PINECONE_API_KEY": "pinecone-api-key",
    "PINECONE_ENVIRONMENT": "pinecone-environment",
    "AZURE_COMMUNICATION_CONNECTION_STRING": "azure-communication-connection-string",
    "AZURE_COMMUNICATION_EMAIL_SENDER": "azure-communication-email-sender",
    "AZURE_COMMUNICATION_SMS_SENDER": "azure-communication-sms-sender",
    "AZURE_AI_PROJECT_ENDPOINT": "azure-ai-project-endpoint",
    "AZURE_AI_SERVICES_ENDPOINT": "azure-ai-services-endpoint",
    "FOUNDRY_GPT_DEPLOYMENT": "foundry-gpt-deployment",
    "FOUNDRY_ROUTER_DEPLOYMENT": "foundry-router-deployment",
    "FOUNDRY_CLAUDE_DEPLOYMENT": "foundry-claude-deployment",
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
    return (
        os.getenv("AZURE_KEY_VAULT_NAME")
        or os.getenv("KEY_VAULT_NAME")
        or DEFAULT_KEY_VAULT_NAME
    ).strip()


def get_key_vault_url() -> str:
    explicit = (os.getenv("AZURE_KEY_VAULT_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/") + "/"
    return f"https://{get_key_vault_name()}.vault.azure.net/"


def get_azure_credential() -> TokenCredential:
    """Resolve Azure credentials for containers, Azure hosts, and local CLI."""
    global _credential
    if _credential is not None:
        return _credential

    tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()
    client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip()

    if tenant_id and client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    elif is_running_on_azure():
        _credential = (
            ManagedIdentityCredential(client_id=client_id)
            if client_id
            else ManagedIdentityCredential()
        )
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
    except (ClientAuthenticationError, HttpResponseError, OSError, ValueError) as exc:
        logger.warning("Key Vault secret %s unavailable: %s", secret_name, exc)
        return None
    except Exception as exc:  # noqa: BLE001 — never crash app import on vault issues
        logger.warning("Key Vault secret %s failed: %s", secret_name, exc)
        return None


def create_provisioning_secret_client(vault_url: str) -> SecretClient:
    """Return a SecretClient for admin/provisioning tasks (e.g. seeding secrets)."""
    from azure.identity import DefaultAzureCredential

    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
