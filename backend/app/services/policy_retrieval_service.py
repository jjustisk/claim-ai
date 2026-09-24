"""Runtime PDS clause retrieval: given a damage description and the
claimant's product, return the most relevant clause(s).

Listwise ranking: one search returns several candidates, then a single
model call ranks them together rather than judging each in isolation
against a fixed threshold.
"""

from __future__ import annotations
import re
from enum import Enum

from pydantic import BaseModel, Field

from app.connectors.chromadb_store import get_pds_clauses_collection
from app.connectors.foundry import embed_texts, get_gpt_client, get_mini_deployment

# {term: meaning} pairs, cached per product_id.
_definitions_cache: dict[int, list[tuple[str, str]]] = {}

DEFAULT_MAX_K = 8

# Distance bar for surfacing a linked exclusion clause.
LINKED_EXCLUSION_DISTANCE = 0.75

class RetrievalAction(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    AMBIGUOUS = "ambiguous"


class RankedMatch(BaseModel):
    action: RetrievalAction
    best_match_id: str | None = Field(
        description="The id of the single best-matching candidate, or null if none apply (action=incorrect)."
    )
    reasoning: str = Field(description="Brief justification for the pick and classification.")


def retrieve_clauses(
    query_text: str,
    *,
    product_id: int,
    max_k: int = DEFAULT_MAX_K,
) -> dict:
    """Returns:
            {
                "action": RetrievalAction,
                "matches": [...],  # the picked clause, refined - empty if incorrect
                "linked_exclusions": [...],  # relevant exclusion clause(s), if any
                "linked_definitions": [...],  # {term, meaning} for any defined term referenced, if any
                "needs_human_review": bool,
            }
    """

    if not query_text or not query_text.strip():
        return _no_match_result()

    # Embed once, reuse for every _search()/_linked_exclusions() call below.
    [embedding] = embed_texts([query_text])

    matches = _search(embedding, product_id=product_id, max_k=max_k)
    if not matches:
        return _no_match_result()

    ranked = _rank_candidates(query_text, matches)

    if ranked.action is RetrievalAction.INCORRECT or ranked.best_match_id is None:
        return {
            "action": RetrievalAction.INCORRECT,
            "matches": [],
            "linked_exclusions": [],
            "linked_definitions": [],
            "needs_human_review": True,
        }

    best = next((m for m in matches if m["id"] == ranked.best_match_id), matches[0])
    refined = _refine(query_text, [best])
    return {
        "action": ranked.action,
        "matches": refined,
        "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
        "linked_definitions": _linked_definitions([best], product_id=product_id),
        # Ambiguous means the model itself wasn't fully confident even in
        # its own best pick - route for review rather than auto-approve.
        "needs_human_review": ranked.action is RetrievalAction.AMBIGUOUS,
    }


def _no_match_result() -> dict:
    return {
        "action": RetrievalAction.INCORRECT,
        "matches": [],
        "linked_exclusions": [],
        "linked_definitions": [],
        "needs_human_review": True,
    }


def _search(embedding: list[float], *, product_id: int | None, max_k: int) -> list[dict]:
    collection = get_pds_clauses_collection()
    where = {"product_id": product_id} if product_id is not None else None
    result = collection.query(query_embeddings=[embedding], where=where, n_results=max_k)

    ids = result.get("ids", [[]])[0]
    if not ids:
        return []
    documents = result.get("documents", [[]])[0]
    metadata = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    return [
        {"id": i, "text": d, "metadata": m, "distance": dist}
        for i, d, m, dist in zip(ids, documents, metadata, distances)
    ]

def _linked_exclusions(embedding: list[float], *, product_id: int) -> list[dict]:
    """Return exclusion clauses for this product that are within
    LINKED_EXCLUSION_DISTANCE of the given embedding."""
    collection = get_pds_clauses_collection()
    result = collection.query(
        query_embeddings=[embedding],
        where={"$and": [{"product_id": product_id}, {"chunk_type": "exclusion"}]},
        n_results=2,
    )
    ids = result.get("ids", [[]])[0]
    if not ids:
        return []
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    return [
        {"id": i, "text": d, "metadata": m, "distance": dist}
        for i, d, m, dist in zip(ids, documents, metadatas, distances)
        if dist <= LINKED_EXCLUSION_DISTANCE
    ]


def _get_definitions(product_id: int) -> list[tuple[str, str]]:
    """Parse the product's Term | Meaning table chunk into (term, meaning)
    pairs, cached per product_id."""
    cached = _definitions_cache.get(product_id)
    if cached is not None:
        return cached

    collection = get_pds_clauses_collection()
    result = collection.get(
        where={"$and": [{"product_id": product_id}, {"chunk_type": "definition"}]},
        include=["documents"],
    )
    pairs: list[tuple[str, str]] = []
    for doc in result.get("documents", []) or []:
        for line in (doc or "").split("\n"):
            if " | " not in line:
                continue
            term, _, meaning = line.partition(" | ")
            term, meaning = term.strip(), meaning.strip()
            if not term or not meaning or term.lower() == "term":
                continue
            pairs.append((term, meaning))

    _definitions_cache[product_id] = pairs
    return pairs


def _linked_definitions(matches: list[dict], *, product_id: int) -> list[dict]:
    """Return {term, meaning} for any defined term referenced (whole-word
    match) in the given matches' text."""
    text = " ".join(m["text"] for m in matches)
    if not text:
        return []
    found = []
    for term, meaning in _get_definitions(product_id):
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            found.append({"term": term, "meaning": meaning})
    return found


def _rank_candidates(query_text: str, matches: list[dict]) -> RankedMatch:
    """Listwise ranking: every candidate is shown to the model together in
    one call, so it can compare them directly rather than judging each in
    isolation"""
    candidates = "\n\n".join(f"[id={m['id']}] {m['text']}" for m in matches)
    response = get_gpt_client().responses.parse(
        model=get_mini_deployment(),
        input=[{"role": "user", "content": (
            f"Query (claim description): {query_text}\n\n"
            f"Candidate policy clauses:\n{candidates}\n\n"
            "Pick the id of the single best-matching clause, and classify the match as:\n"
            "correct - clearly and directly applicable\n"
            "ambiguous - plausibly relevant but not clearly decisive\n"
            "incorrect - none of these candidates actually apply (leave best_match_id null)"
        )}],
        text_format=RankedMatch,
    )
    return response.output_parsed


def _refine(query_text: str, matches: list[dict]) -> list[dict]:
    """Decompose-then-recompose: split the matched clause, keep only strips relevant to the query, recompose.
    Simple heuristic version: keep sentences that share a significant word with the query.
    """
    query_words = {w.lower() for w in query_text.split() if len(w) > 3}
    refined = []
    for match in matches:
        sentences = [s.strip() for s in match["text"].split(".") if s.strip()]
        kept = [
                s for s in sentences
                if query_words & {w.lower().strip(",;:") for w in s.split()}
        ] or sentences
        refined.append({**match, "text": ". ".join(kept)})
    return refined
