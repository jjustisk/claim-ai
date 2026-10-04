"""FIFO background queue for post-submit claim processing (PII + AI).

Submit returns as soon as the claim is saved. Each claim_id is processed one at
a time in order so concurrent submits do not stampede Foundry / PII.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from app.connectors.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] | None = None
_worker_task: asyncio.Task | None = None
_pending: set[int] = set()
_order: deque[int] = deque()
_lock = asyncio.Lock()


def _ensure_queue() -> asyncio.Queue[int]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def start_claim_pipeline_worker() -> None:
    """Start the single background worker (call once from app lifespan)."""
    global _worker_task
    _ensure_queue()
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop(), name="claim-pipeline-worker")
    logger.info("Claim pipeline queue worker started")


async def stop_claim_pipeline_worker() -> None:
    """Stop the worker on shutdown (best-effort; in-flight job may finish)."""
    global _worker_task, _queue
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    _queue = None
    logger.info("Claim pipeline queue worker stopped")


async def enqueue_claim_pipeline(claim_id: int) -> dict[str, int | bool]:
    """Queue a submitted claim for background PII + AI processing.

    Duplicate enqueue of the same claim_id while still pending is ignored.
    Returns queue position metadata for logging / API extras.
    """
    q = _ensure_queue()
    async with _lock:
        if claim_id in _pending:
            position = list(_order).index(claim_id) + 1 if claim_id in _order else 0
            logger.info(
                "Claim pipeline already queued claim_id=%s position=%s",
                claim_id,
                position,
            )
            return {"queued": True, "duplicate": True, "queue_position": position, "queue_size": len(_order)}

        _pending.add(claim_id)
        _order.append(claim_id)
        position = len(_order)

    await q.put(claim_id)
    logger.info(
        "Claim pipeline enqueued claim_id=%s queue_position=%s queue_size=%s",
        claim_id,
        position,
        position,
    )
    return {"queued": True, "duplicate": False, "queue_position": position, "queue_size": position}


def pipeline_queue_snapshot() -> dict[str, int | list[int]]:
    return {
        "queue_size": len(_order),
        "pending_claim_ids": list(_order),
    }


async def _worker_loop() -> None:
    q = _ensure_queue()
    while True:
        claim_id = await q.get()
        try:
            async with _lock:
                if _order and _order[0] == claim_id:
                    _order.popleft()
                elif claim_id in _order:
                    _order.remove(claim_id)

            logger.info("Claim pipeline processing started claim_id=%s", claim_id)
            await _process_claim(claim_id)
            logger.info("Claim pipeline processing finished claim_id=%s", claim_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Claim pipeline processing failed claim_id=%s", claim_id)
        finally:
            async with _lock:
                _pending.discard(claim_id)
            q.task_done()


async def _process_claim(claim_id: int) -> None:
    from app.services.ai_pipeline_service import run_decision_pipeline

    async with AsyncSessionLocal() as db:
        await run_decision_pipeline(claim_id, db)
