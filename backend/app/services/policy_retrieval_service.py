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
import re
from enum import Enum

from app.connectors.chromadb_store import get_pds_clauses_collection
from app.connectors.foundry import embed_texts

# {term: meaning} pairs, cached per product_id.
_definitions_cache: dict[int, list[tuple[str, str]]] = {}

DEFAULT_MAX_K = 5
DEFAULT_GAP_THRESHOLD = 0.15

# Absolute cosine-distance thresholds for classifying a retrieval.
CORRECT_DISTANCE = 0.30 # top match closer than this -> confidently relevant
INCORRECT_DISTANCE = 0.45 # top match farther than this -> confidently irrelevant

BROADENED_MAX_K = 10 # if top match is confidently irrelevant, broaden search to this many results

# Distance bar for surfacing a linked exclusion clause.
LINKED_EXCLUSION_DISTANCE = 0.75

class RetrievalAction(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    AMBIGUOUS = "ambiguous"
    

def retrieve_clauses(
    query_text: str,
    *,
    product_id: int,
    max_k: int = DEFAULT_MAX_K,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> dict:
    """CRAG-gated retrieval. Returns:
            {
                "action": RetrievalAction,
                "matches": [...],
                "linked_exclusions": [...],  # relevant exclusion clause(s), if any
                "linked_definitions": [...],  # {term, meaning} for any defined term referenced, if any
                "needs_human_review": bool,
            }
    """

    if not query_text or not query_text.strip():
        return {
            "action": RetrievalAction.INCORRECT,
            "matches": [],
            "linked_exclusions": [],
            "linked_definitions": [],
            "needs_human_review": True,
        }

    # Embed once, reuse for every _search()/_linked_exclusions() call below.
    [embedding] = embed_texts([query_text])

    matches = _search(embedding, product_id=product_id, max_k=max_k)
    if not matches:
        return {
            "action": RetrievalAction.INCORRECT,
            "matches": [],
            "linked_exclusions": [],
            "linked_definitions": [],
            "needs_human_review": True,
        }

    action = _classify(matches[0]["distance"])

    if action == RetrievalAction.CORRECT:
        refined = _refine(query_text, matches[:1])
        return {
            "action": action,
            "matches": refined,
            "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
            "linked_definitions": _linked_definitions(matches[:1], product_id=product_id),
            "needs_human_review": False,
        }

    if action is RetrievalAction.AMBIGUOUS:
        refined_top = _refine(query_text, matches[:1])
        # Widen k, but never drop product_id - each product's PDS is a
        # separate contract, so a clause from a different product is never
        # actually applicable to this claim no matter how close its distance.
        broadened = _search(embedding, product_id=product_id, max_k=BROADENED_MAX_K)
        broadened_action = _classify(broadened[0]["distance"]) if broadened else RetrievalAction.INCORRECT

        if broadened_action is RetrievalAction.INCORRECT:
            kept = _apply_score_gap_threshold(matches, gap_threshold, max_k)
            return {
                "action": action,
                "matches": kept,
                "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
                "linked_definitions": _linked_definitions(kept, product_id=product_id),
                "needs_human_review": True,
            }

        combined = _combine(refined_top, broadened, max_k)
        return {
            "action": action,
            "matches": combined,
            "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
            "linked_definitions": _linked_definitions(matches[:1] + broadened, product_id=product_id),
            "needs_human_review": False,
        }

    # INCORRECT: broaden once by widening k (never by dropping product_id -
    # see note above) then reclassify.
    broadened = _search(embedding, product_id=product_id, max_k=BROADENED_MAX_K)
    broadened_action = _classify(broadened[0]["distance"]) if broadened else RetrievalAction.INCORRECT

    if broadened_action is RetrievalAction.CORRECT:
        refined = _refine(query_text, broadened[:1])
        return {
            "action": RetrievalAction.CORRECT,
            "matches": refined,
            "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
            "linked_definitions": _linked_definitions(broadened[:1], product_id=product_id),
            "needs_human_review": False,
        }

    if broadened_action is RetrievalAction.AMBIGUOUS:
        kept = _apply_score_gap_threshold(broadened, gap_threshold, max_k)
        return {
            "action": RetrievalAction.AMBIGUOUS,
            "matches": kept,
            "linked_exclusions": _linked_exclusions(embedding, product_id=product_id),
            "linked_definitions": _linked_definitions(kept, product_id=product_id),
            "needs_human_review": False,
        }

    # Still incorrect after broadening: escalate to a human.
    return {
        "action": RetrievalAction.INCORRECT,
        "matches": matches[:max_k],
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


def _classify(top_distance: float) -> RetrievalAction:
    if top_distance < CORRECT_DISTANCE:
        return RetrievalAction.CORRECT
    if top_distance > INCORRECT_DISTANCE:
        return RetrievalAction.INCORRECT
    return RetrievalAction.AMBIGUOUS

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

def _combine(internal: list[dict], external: list[dict], max_k: int) -> list[dict]:
    """Merge two match lists, de-duplicating by id, keeping internal matches first."""
    seen_ids = {m["id"] for m in internal}
    combined = list(internal)
    for m in external:
        if len(combined) >= max_k:
            break
        if m["id"] not in seen_ids:
            combined.append(m)
            seen_ids.add(m["id"])
    return combined


def _apply_score_gap_threshold(
    matches: list[dict], gap_threshold: float, max_k: int
) -> list[dict]:
    if len(matches) <= 1:
        return matches
    gap = matches[1]["distance"] - matches[0]["distance"]
    if gap > gap_threshold:
        return [matches[0]]
    return matches[:max_k]
