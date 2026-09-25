"""Rehydration service with policy controls."""

from __future__ import annotations

from typing import Any

from app.schemas.claims import RehydrationPolicy
from app.services.audit.logger import get_audit_logger
from app.services.pii.placeholders import rehydrate_structure
from app.services.storage.session_store import SessionStorage


class RehydrationService:
    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()
        self.audit = get_audit_logger()

    def rehydrate(
        self,
        session_id: str,
        content: str | dict[str, Any],
        policy: RehydrationPolicy = RehydrationPolicy.FULL,
        allowed_entities: list[str] | None = None,
    ) -> dict[str, Any]:
        self.audit.log("REHYDRATION_REQUESTED", session_id=session_id, policy=policy.value)
        mapping = self.storage.load_mapping(session_id)

        if policy == RehydrationPolicy.NONE:
            self.audit.log("REHYDRATION_COMPLETED", session_id=session_id, policy="NONE")
            return {
                "status": "REHYDRATED",
                "rehydrated": content,
                "unknown_placeholders": [],
            }

        allowed_prefixes: set[str] | None = None
        if policy == RehydrationPolicy.LIMITED:
            allowed_prefixes = set(allowed_entities or [])

        rehydrated, unknown = rehydrate_structure(content, mapping, allowed_prefixes)
        # Deduplicate unknowns while preserving order
        seen: set[str] = set()
        unique_unknown: list[str] = []
        for token in unknown:
            if token not in seen:
                seen.add(token)
                unique_unknown.append(token)

        status = "REHYDRATION_WARNING" if unique_unknown else "REHYDRATED"
        self.audit.log(
            "REHYDRATION_COMPLETED",
            session_id=session_id,
            status=status,
            unknown_count=len(unique_unknown),
        )
        return {
            "status": status,
            "rehydrated": rehydrated,
            "unknown_placeholders": unique_unknown,
        }
