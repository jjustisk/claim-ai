"""Encryption provider abstraction."""

from __future__ import annotations

import base64
import logging
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_KEY_FILE = Path("data") / ".fernet_key"


class EncryptionProvider(ABC):
    @abstractmethod
    def encrypt(self, value: bytes | str) -> bytes:
        ...

    @abstractmethod
    def decrypt(self, value: bytes) -> bytes:
        ...

    def encrypt_text(self, value: str) -> str:
        return base64.urlsafe_b64encode(self.encrypt(value.encode("utf-8"))).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        return self.decrypt(base64.urlsafe_b64decode(value.encode("ascii"))).decode("utf-8")


class FernetEncryptionProvider(EncryptionProvider):
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, value: bytes | str) -> bytes:
        data = value.encode("utf-8") if isinstance(value, str) else value
        return self._fernet.encrypt(data)

    def decrypt(self, value: bytes) -> bytes:
        try:
            return self._fernet.decrypt(value)
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt payload") from exc


def _resolve_dev_key() -> str:
    """Stable dev key across reloads — avoids orphaning encrypted raw uploads."""
    env_key = os.environ.get("CLAIM_AI_ENCRYPTION_KEY") or os.environ.get("ENCRYPTION_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    if _KEY_FILE.is_file():
        stored = _KEY_FILE.read_text(encoding="ascii").strip()
        if stored:
            os.environ["CLAIM_AI_ENCRYPTION_KEY"] = stored
            return stored

    key = Fernet.generate_key().decode("ascii")
    try:
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_text(key, encoding="ascii")
        logger.warning(
            "Generated Fernet key and saved to %s (dev only). Set CLAIM_AI_ENCRYPTION_KEY for production.",
            _KEY_FILE,
        )
    except OSError as exc:
        logger.warning("Could not persist Fernet key (%s); key is process-local only", exc)
    os.environ["CLAIM_AI_ENCRYPTION_KEY"] = key
    return key


@lru_cache
def get_encryption_provider() -> EncryptionProvider:
    settings = get_settings()
    key = settings.encryption_key
    if not key or not str(key).strip():
        key = _resolve_dev_key()
    return FernetEncryptionProvider(key.encode("ascii") if isinstance(key, str) else key)
