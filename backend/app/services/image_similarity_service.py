"""Image-similarity fraud sub-score, based on perceptual hashing.

Contains the hash computation used at upload time and the comparison used
at scoring time. Comparison runs as SQL against Postgres bit(64) columns
(bit_count(a # b) - XOR then popcount), not in Python, since a brute-force
Python comparison against every other claim's images doesn't scale.
"""

from __future__ import annotations

import asyncio
import io

import imagehash
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.damage_description_services import IMAGE_FILE_TYPES

def compute_phash_bits(image_bytes: bytes) -> str:
    """Computes a 64-character bit string perceptual hash for one image's raw bytes."""
    hash_obj = imagehash.phash(Image.open(io.BytesIO(image_bytes)))
    return "".join("1" if bit else "0" for bit in hash_obj.hash.flatten())


async def store_phash(db: AsyncSession, doc_id: int, image_bytes: bytes) -> None:
    """Computes and stores one document's perceptual hash; skips silently on a bad image."""
    try:
        phash_bits = await asyncio.to_thread(compute_phash_bits, image_bytes)
    except Exception:
        return
    await db.execute(
        text("UPDATE claim_document SET phash = CAST(:bits AS bit(64)) WHERE doc_id = :doc_id"),
        {"bits": phash_bits, "doc_id": doc_id},
    )


def _image_similarity_threshold(hamming_distance: int) -> float:
    """Maps a Hamming distance to its image-similarity risk score threshold."""
    if hamming_distance <= 5:
        return 1.0
    if hamming_distance <= 15:
        return 0.5
    return 0.0


async def _claim_image_hashes(db: AsyncSession, claim_id: int) -> list[tuple[int, str]]:
    """Returns (doc_id, phash) for a claim's own hashed images."""
    result = await db.execute(
        text(
            "SELECT doc_id, phash::text AS phash FROM claim_document "
            "WHERE claim_id = :claim_id AND phash IS NOT NULL"
        ),
        {"claim_id": claim_id},
    )
    return [(row.doc_id, row.phash) for row in result]


async def _closest_match(
    db: AsyncSession, own_hash: str, exclude_claim_id: int
) -> tuple[int, int, int] | None:
    """Finds the other claim's image with the smallest Hamming distance to one hash."""
    result = await db.execute(
        text(
            "SELECT claim_id, doc_id, bit_count(phash # CAST(:own_hash AS bit(64))) AS distance "
            "FROM claim_document WHERE claim_id != :exclude_claim_id AND phash IS NOT NULL "
            "ORDER BY distance ASC LIMIT 1"
        ),
        {"own_hash": own_hash, "exclude_claim_id": exclude_claim_id},
    )
    row = result.first()
    return (row.claim_id, row.doc_id, row.distance) if row else None


async def image_similarity_score(db: AsyncSession, claim_id: int) -> dict:
    """Computes a claim's image-similarity fraud score across all its images."""
    own_hashes = await _claim_image_hashes(db, claim_id)
    if not own_hashes:
        return {"closest_match": None, "hamming_distance": None, "image_similarity_score": 0.0}

    best: tuple[int, int, int, int] | None = None
    for own_doc_id, own_hash in own_hashes:
        match = await _closest_match(db, own_hash, claim_id)
        if match and (best is None or match[2] < best[3]):
            best = (own_doc_id, *match)

    if best is None:
        return {"closest_match": None, "hamming_distance": None, "image_similarity_score": 0.0}

    own_doc_id, matched_claim_id, matched_doc_id, distance = best
    return {
        "closest_match": {
            "own_doc_id": own_doc_id,
            "matched_claim_id": matched_claim_id,
            "matched_doc_id": matched_doc_id,
        },
        "hamming_distance": distance,
        "image_similarity_score": _image_similarity_threshold(distance),
    }


__all__ = ["compute_phash_bits", "store_phash", "image_similarity_score", "IMAGE_FILE_TYPES"]
