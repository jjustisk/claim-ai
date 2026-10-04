"""ChromaDB connection and collection access."""

from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.config import settings

_client: ClientAPI | None = None

PDS_CLAUSES_COLLECTION = "pds_clauses"


def _http_client_settings() -> ChromaSettings | None:
    """Build client auth settings when a Chroma server token is configured."""
    token = (settings.chroma_auth_token or "").strip()
    if not token:
        return None
    return ChromaSettings(
        chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
        chroma_client_auth_credentials=token,
        chroma_auth_token_transport_header="Authorization",
    )


def get_chroma_client() -> ClientAPI:
    """Return a shared ChromaDB client (HTTP server or local persistent storage)."""
    global _client
    if _client is None:
        if settings.chroma_host:
            auth_settings = _http_client_settings()
            _client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=auth_settings,
            )
        else:
            persist_dir = Path(settings.chroma_persist_directory)
            persist_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(persist_dir))
    return _client


def get_collection(name: str | None = None) -> Collection:
    """Return a ChromaDB collection, creating it if needed."""
    collection_name = name or settings.chroma_collection_name
    return get_chroma_client().get_or_create_collection(name=collection_name)


def get_pds_clauses_collection() -> Collection:
    """Return the shared collection holding chunked PDS clauses, using cosine distance."""
    return get_chroma_client().get_or_create_collection(
        name=PDS_CLAUSES_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def reset_chroma_client() -> None:
    """Clear the cached client (useful in tests)."""
    global _client
    _client = None
