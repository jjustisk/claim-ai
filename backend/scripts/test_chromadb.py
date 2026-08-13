"""Verify ChromaDB connection and basic read/write operations.

Uses local persistent storage by default (see CHROMA_* in .env.example).
Set CHROMA_HOST to connect to a remote Chroma server instead.

Run from backend/:
    python scripts/test_chromadb.py
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chromadb_store import get_chroma_client, get_collection, reset_chroma_client
from app.config import settings

TEST_DOC = "ChromaDB is working for Claim AI."
TEST_ID_PREFIX = "connection-test"


def _connection_mode() -> str:
    if settings.chroma_host:
        return f"HTTP ({settings.chroma_host}:{settings.chroma_port})"
    return f"local persistent ({settings.chroma_persist_directory})"


def main() -> int:
    print("ChromaDB connection test")
    print(f"  Mode: {settings.chroma_collection_name} @ {_connection_mode()}")

    test_id = f"{TEST_ID_PREFIX}-{uuid.uuid4().hex[:8]}"

    try:
        client = get_chroma_client()
        heartbeat = client.heartbeat()
        print(f"  Heartbeat: {heartbeat} ns")

        collection = get_collection()
        print(f"  Collection: {collection.name} ({collection.count()} existing documents)")

        collection.upsert(
            ids=[test_id],
            documents=[TEST_DOC],
            metadatas=[{"source": "test_chromadb.py"}],
        )
        print(f"  Upserted test document: {test_id}")

        fetched = collection.get(ids=[test_id], include=["documents", "metadatas"])
        document = fetched["documents"][0] if fetched["documents"] else None
        if document != TEST_DOC:
            print(f"  FAIL: expected document {TEST_DOC!r}, got {document!r}", file=sys.stderr)
            return 1
        print("  Read back document: OK")

        results = collection.query(query_texts=["Claim AI vector store"], n_results=1)
        top_id = results["ids"][0][0] if results["ids"] and results["ids"][0] else None
        if top_id != test_id:
            print(f"  FAIL: query did not return test document (got {top_id!r})", file=sys.stderr)
            return 1
        print("  Query test document: OK")

        collection.delete(ids=[test_id])
        print("  Cleaned up test document")

    except Exception as exc:
        print(f"  FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        reset_chroma_client()

    print("SUCCESS: ChromaDB is working.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
