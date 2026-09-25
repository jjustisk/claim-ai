"""Audit logging — never log raw PII."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import get_settings


class AuditLogger:
    def __init__(self, audit_dir: Path | None = None) -> None:
        settings = get_settings()
        self.audit_dir = audit_dir or settings.storage_paths()["audit"]
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, session_id: str | None = None, **details: Any) -> None:
        # Strip any accidental PII-looking keys
        safe_details = {
            k: v
            for k, v in details.items()
            if k.lower() not in {"raw", "value", "pii", "name", "address", "phone", "email"}
        }
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "session_id": session_id,
            "details": safe_details,
        }
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        path = self.audit_dir / "audit.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def events_for_session(self, session_id: str) -> list[dict[str, Any]]:
        path = self.audit_dir / "audit.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("session_id") == session_id:
                    events.append(record)
        return events


_audit: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit
