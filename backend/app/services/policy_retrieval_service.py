"""Runtime PDS clause retrieval: given a damage description and the
claimant's product, return the most relevant clause(s).

See .claude/plans/stage0-pds-ingestion-retrieval.md for the design
(product-scoped metadata filtering, score-gap thresholding).

Known limitation, deferred: the query text passed in today is expected to
be the VLM's image-derived damage description alone — it has no visibility
into circumstantial context from the claimant's narrative (e.g. what led to
the accident), which several PDS exclusions actually turn on. Revisit once
the Decision LLM prompt is being built.
"""

from __future__ import annotations

from app.connectors.chromadb_store import get_pds_clauses_collection
from app.connectors.foundry import embed_texts

DEFAULT_MAX_K = 5
DEFAULT_GAP_THRESHOLD = 0.15


def retrieve_clauses(
    query_text: str,
    *,
    product_id: int,
    max_k: int = DEFAULT_MAX_K,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> list[dict]:
    """Embed query_text, search pds_clauses scoped to product_id, and apply
    score-gap thresholding: return only rank 1 if the gap to rank 2 is
    large, otherwise return up to max_k results."""
    if not query_text or not query_text.strip():
        return []

    [embedding] = embed_texts([query_text])
    collection = get_pds_clauses_collection()
    result = collection.query(
        query_embeddings=[embedding],
        where={"product_id": product_id},
        n_results=max_k,
    )

    ids = result.get("ids", [[]])[0]
    if not ids:
        return []
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    matches = [
        {"id": i, "text": d, "metadata": m, "distance": dist}
        for i, d, m, dist in zip(ids, documents, metadatas, distances)
    ]
    return _apply_score_gap_threshold(matches, gap_threshold, max_k)


def _apply_score_gap_threshold(
    matches: list[dict], gap_threshold: float, max_k: int
) -> list[dict]:
    if len(matches) <= 1:
        return matches
    gap = matches[1]["distance"] - matches[0]["distance"]
    if gap > gap_threshold:
        return [matches[0]]
    return matches[:max_k]
