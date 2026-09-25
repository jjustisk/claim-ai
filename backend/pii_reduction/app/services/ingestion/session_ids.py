"""Session ID generation."""

from __future__ import annotations

import ulid


def generate_session_id() -> str:
    return f"CLMSESSION_{ulid.new()}"
