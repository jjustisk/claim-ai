"""Enforce retention TTLs for raw uploads, mappings, sanitised artefacts, and audit logs."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.services.audit.logger import get_audit_logger
from app.services.storage.session_store import SessionStorage

logger = logging.getLogger(__name__)


class MappingExpiredError(RuntimeError):
    """Raised when a session mapping has passed its retention TTL."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _path_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


class RetentionService:
    def __init__(
        self,
        settings: Settings | None = None,
        storage: SessionStorage | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or SessionStorage(self.settings)
        self.audit = get_audit_logger()

    def mapping_expires_at(self, session_id: str) -> datetime | None:
        path = self.storage.mapping_dir(session_id) / "mapping.enc"
        mtime = _path_mtime(path)
        hours = self.settings.retention_mapping_hours
        if mtime is None or hours <= 0:
            return None
        return mtime + timedelta(hours=hours)

    def assert_mapping_valid(self, session_id: str) -> None:
        """Refuse rehydration when the encrypted mapping TTL has elapsed."""
        expires = self.mapping_expires_at(session_id)
        if expires is None:
            return
        if _utc_now() >= expires:
            self.audit.log("MAPPING_EXPIRED", session_id=session_id)
            raise MappingExpiredError(
                f"Placeholder mapping for {session_id} expired at {expires.isoformat()}"
            )

    def sweep(self) -> dict[str, int]:
        """Delete artefacts past their configured retention windows. Returns counts."""
        counts = {"raw": 0, "mapping": 0, "sanitised": 0, "audit": 0, "sessions": 0}
        now = _utc_now()
        paths = self.settings.storage_paths()

        counts["raw"] += self._sweep_tree(
            paths["raw"], self.settings.retention_raw_hours, now
        )
        counts["mapping"] += self._sweep_tree(
            paths["secure_mapping"], self.settings.retention_mapping_hours, now
        )
        counts["sanitised"] += self._sweep_tree(
            paths["sanitised"], self.settings.retention_sanitised_hours, now
        )
        # llm-ready follows sanitised retention (same privacy artefacts)
        counts["sanitised"] += self._sweep_tree(
            paths["llm_ready"], self.settings.retention_sanitised_hours, now
        )
        counts["audit"] += self._sweep_audit(paths["audit"], now)
        counts["sessions"] += self._sweep_orphan_sessions(paths["sessions"], now)

        if any(counts.values()):
            self.audit.log("RETENTION_SWEEP", **counts)
        return counts

    def _expired(self, path: Path, hours: int, now: datetime) -> bool:
        if hours <= 0:
            return False
        mtime = _path_mtime(path)
        if mtime is None:
            return False
        return now >= mtime + timedelta(hours=hours)

    def _sweep_tree(self, root: Path, hours: int, now: datetime) -> int:
        if hours <= 0 or not root.exists():
            return 0
        removed = 0
        for child in list(root.iterdir()):
            if not child.is_dir():
                continue
            # Use newest file mtime inside the session folder
            newest = _path_mtime(child)
            for p in child.rglob("*"):
                if p.is_file():
                    mt = _path_mtime(p)
                    if mt and (newest is None or mt > newest):
                        newest = mt
            if newest is None:
                continue
            if now >= newest + timedelta(hours=hours):
                try:
                    shutil.rmtree(child)
                    removed += 1
                except OSError as exc:
                    logger.warning("Retention delete failed for %s: %s", child, exc)
        return removed

    def _sweep_audit(self, audit_dir: Path, now: datetime) -> int:
        hours = self.settings.retention_audit_hours
        if hours <= 0 or not audit_dir.exists():
            return 0
        removed = 0
        for path in list(audit_dir.glob("*.jsonl")):
            if self._expired(path, hours, now):
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    logger.warning("Audit retention delete failed for %s: %s", path, exc)
        return removed

    def _sweep_orphan_sessions(self, sessions_dir: Path, now: datetime) -> int:
        """Drop session records whose mapping + sanitised data are both gone / expired."""
        hours = max(
            self.settings.retention_mapping_hours,
            self.settings.retention_sanitised_hours,
            self.settings.retention_raw_hours,
        )
        if hours <= 0 or not sessions_dir.exists():
            return 0
        removed = 0
        for child in list(sessions_dir.iterdir()):
            if not child.is_dir():
                continue
            session_json = child / "session.json"
            if not self._expired(session_json if session_json.exists() else child, hours, now):
                continue
            mapping_exists = (self.storage.mapping_dir(child.name) / "mapping.enc").exists()
            sanitised_exists = self.storage.sanitised_dir(child.name).exists()
            if mapping_exists or sanitised_exists:
                continue
            try:
                shutil.rmtree(child)
                removed += 1
            except OSError as exc:
                logger.warning("Session retention delete failed for %s: %s", child, exc)
        return removed
