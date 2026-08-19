"""ChromaDB connection and collection access."""

from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from app.config import settings

_client: ClientAPI | None = None


def get_chroma_client() -> ClientAPI:
    """Return a shared ChromaDB client (HTTP server or local persistent storage)."""
    global _client
    if _client is None:
        if settings.chroma_host:
            _client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
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


def reset_chroma_client() -> None:
    """Clear the cached client (useful in tests)."""
    global _client
    _client = None
