"""Azure AI Foundry connection for hosted language models.

GPT 5.5 and Claude Opus are accessed through this module via your Foundry
project. The app does not call OpenAI or Anthropic directly — auth uses Azure
login (managed identity or `az login`).

In australiaeast, Claude Opus is not deployable directly. Use the model-router
deployment (quality mode) for the Claude slot; the router picks the best model
available in-region (GPT today, Claude when deployable).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from anthropic import AnthropicFoundry
from azure.ai.projects import AIProjectClient
from azure.identity import get_bearer_token_provider

from app.config import settings
from app.secrets import get_azure_credential

if TYPE_CHECKING:
    from openai import OpenAI

# Model IDs in the Azure AI Foundry catalog.
GPT_MODEL = "gpt-5.5"
CLAUDE_MODEL = "claude-opus-4-8"
ROUTER_DEPLOYMENT = "model-router"

_project_client: AIProjectClient | None = None
_gpt_client: OpenAI | None = None
_claude_client: AnthropicFoundry | None = None
_credential = None


def _get_credential():
    """Reuse the shared Azure credential (CLI locally, managed identity on Azure)."""
    global _credential
    if _credential is None:
        _credential = get_azure_credential()
    return _credential


def _require_project_endpoint() -> str:
    if not settings.azure_ai_project_endpoint:
        raise RuntimeError(
            "AZURE_AI_PROJECT_ENDPOINT is not set. "
            "Add it to your .env file or Key Vault to use Azure AI Foundry."
        )
    return settings.azure_ai_project_endpoint


def _services_endpoint() -> str:
    if settings.azure_ai_services_endpoint:
        return settings.azure_ai_services_endpoint.rstrip("/")

    project_endpoint = _require_project_endpoint().rstrip("/")
    marker = "/api/projects/"
    if marker in project_endpoint:
        return project_endpoint.split(marker)[0]
    return project_endpoint


def get_foundry_project_client() -> AIProjectClient:
    """Return a shared Azure AI Foundry project client."""
    global _project_client
    if _project_client is None:
        _project_client = AIProjectClient(
            endpoint=_require_project_endpoint(),
            credential=_get_credential(),
        )
    return _project_client


def get_gpt_client() -> OpenAI:
    """Return the OpenAI-compatible client for Foundry chat models."""
    global _gpt_client
    if _gpt_client is None:
        _gpt_client = get_foundry_project_client().get_openai_client()
    return _gpt_client


def get_claude_client() -> AnthropicFoundry:
    """Return the Anthropic client for a direct Claude deployment."""
    global _claude_client
    if _claude_client is None:
        token_provider = get_bearer_token_provider(
            _get_credential(),
            "https://ai.azure.com/.default",
        )
        _claude_client = AnthropicFoundry(
            azure_ad_token_provider=token_provider,
            base_url=f"{_services_endpoint()}/anthropic",
        )
    return _claude_client


def get_gpt_deployment() -> str:
    """Return the Foundry deployment name for GPT 5.5."""
    return settings.foundry_gpt_deployment or GPT_MODEL


def get_router_deployment() -> str:
    """Return the Foundry model-router deployment name."""
    return settings.foundry_router_deployment or ROUTER_DEPLOYMENT


def get_claude_deployment() -> str:
    """Return the deployment used for Claude Opus requests."""
    return settings.foundry_claude_deployment or get_router_deployment()


def uses_claude_router() -> bool:
    """True when Claude requests go through model-router instead of /anthropic."""
    return get_claude_deployment() == get_router_deployment()


def create_claude_response(prompt: str, **kwargs: Any) -> Any:
    """Send a Claude Opus request through Foundry model-router."""
    return get_gpt_client().responses.create(
        model=get_claude_deployment(),
        input=prompt,
        **kwargs,
    )


def stream_response_text(deployment: str, prompt: str, **kwargs: Any) -> Iterator[str]:
    """Stream model output token-by-token from the Responses API."""
    with get_gpt_client().responses.stream(
        model=deployment,
        input=prompt,
        **kwargs,
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta
        stream.until_done()


def warm_deployment(deployment: str) -> None:
    """Pre-warm auth, HTTP connections, and routing before the first prompt."""
    with get_gpt_client().responses.stream(
        model=deployment,
        input="hi",
    ) as stream:
        stream.until_done()


def warm_gpt_client() -> None:
    """Pre-warm the GPT deployment."""
    warm_deployment(get_gpt_deployment())


def warm_claude_client() -> None:
    """Pre-warm the Claude/router deployment."""
    warm_deployment(get_claude_deployment())


def reset_foundry_clients() -> None:
    """Clear cached clients (useful in tests)."""
    global _project_client, _gpt_client, _claude_client, _credential
    _project_client = None
    _gpt_client = None
    _claude_client = None
    _credential = None
