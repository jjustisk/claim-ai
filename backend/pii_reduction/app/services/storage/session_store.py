"""Session-scoped filesystem storage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.config.settings import Settings, get_settings
from app.models.session import ClaimSession
from app.services.encryption.provider import EncryptionProvider, get_encryption_provider


class SessionStorage:
    def __init__(
        self,
        settings: Settings | None = None,
        encryption: EncryptionProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.encryption = encryption or get_encryption_provider()
        self.paths = self.settings.storage_paths()
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        return self.paths["sessions"] / session_id

    def raw_dir(self, session_id: str) -> Path:
        return self.paths["raw"] / session_id

    def sanitised_dir(self, session_id: str) -> Path:
        return self.paths["sanitised"] / session_id

    def mapping_dir(self, session_id: str) -> Path:
        return self.paths["secure_mapping"] / session_id

    def llm_ready_dir(self, session_id: str) -> Path:
        return self.paths["llm_ready"] / session_id

    def ensure_session_dirs(self, session_id: str) -> None:
        for d in (
            self.session_dir(session_id),
            self.raw_dir(session_id),
            self.sanitised_dir(session_id) / "images",
            self.sanitised_dir(session_id) / "documents",
            self.sanitised_dir(session_id) / "ocr",
            self.mapping_dir(session_id),
            self.llm_ready_dir(session_id),
        ):
            d.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: ClaimSession) -> None:
        self.ensure_session_dirs(session.session_id)
        path = self.session_dir(session.session_id) / "session.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def load_session(self, session_id: str) -> ClaimSession | None:
        path = self.session_dir(session_id) / "session.json"
        if not path.exists():
            return None
        return ClaimSession.model_validate_json(path.read_text(encoding="utf-8"))

    def write_raw_bytes(self, session_id: str, relative: str, data: bytes) -> Path:
        target = self.raw_dir(session_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self.encryption.encrypt(data)
        target.write_bytes(encrypted)
        return target

    def write_raw_json(self, session_id: str, relative: str, payload: dict[str, Any]) -> Path:
        return self.write_raw_bytes(
            session_id,
            relative,
            json.dumps(payload, indent=2).encode("utf-8"),
        )

    def read_raw_bytes(self, session_id: str, relative: str) -> bytes:
        target = self.raw_dir(session_id) / relative
        return self.encryption.decrypt(target.read_bytes())

    def write_sanitised_bytes(self, session_id: str, relative: str, data: bytes) -> Path:
        target = self.sanitised_dir(session_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_sanitised_text(self, session_id: str, relative: str, text: str) -> Path:
        return self.write_sanitised_bytes(session_id, relative, text.encode("utf-8"))

    def write_sanitised_json(self, session_id: str, relative: str, payload: dict[str, Any]) -> Path:
        return self.write_sanitised_text(
            session_id,
            relative,
            json.dumps(payload, indent=2),
        )

    def save_mapping(self, session_id: str, mapping: dict[str, str]) -> Path:
        """Store placeholder mapping encrypted — never in llm-ready."""
        self.ensure_session_dirs(session_id)
        path = self.mapping_dir(session_id) / "mapping.enc"
        encrypted = self.encryption.encrypt(json.dumps(mapping).encode("utf-8"))
        path.write_bytes(encrypted)
        return path

    def load_mapping(self, session_id: str) -> dict[str, str]:
        path = self.mapping_dir(session_id) / "mapping.enc"
        if not path.exists():
            return {}
        raw = self.encryption.decrypt(path.read_bytes())
        return json.loads(raw.decode("utf-8"))

    def write_llm_payload(self, session_id: str, payload: dict[str, Any]) -> Path:
        path = self.llm_ready_dir(session_id) / "payload.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def read_llm_payload(self, session_id: str) -> dict[str, Any] | None:
        path = self.llm_ready_dir(session_id) / "payload.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def copy_to_package(self, session_id: str, package_name: str = "claim_package") -> Path:
        src = self.sanitised_dir(session_id)
        dest = self.llm_ready_dir(session_id) / package_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return dest
