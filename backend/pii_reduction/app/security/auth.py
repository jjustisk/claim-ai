"""Security roles and request authentication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import Header, HTTPException, status

from app.config.settings import Settings, get_settings


class Role(str, Enum):
    PII_PROCESSOR = "PII_PROCESSOR"
    PII_REHYDRATOR = "PII_REHYDRATOR"
    CLAIMS_USER = "CLAIMS_USER"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


ENDPOINT_ROLES: dict[str, set[Role]] = {
    "create_session": {Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN},
    "upload_inputs": {Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN},
    "sanitize": {Role.PII_PROCESSOR, Role.ADMIN},
    "validate": {Role.PII_PROCESSOR, Role.ADMIN},
    "prepare": {Role.PII_PROCESSOR, Role.ADMIN},
    "llm_payload": {Role.PII_PROCESSOR, Role.CLAIMS_USER, Role.ADMIN},
    "rehydrate": {Role.PII_REHYDRATOR, Role.ADMIN},
}


@dataclass(frozen=True)
class AuthenticatedCaller:
    role: Role
    api_key_id: str


def resolve_caller(
    x_api_key: str | None,
    x_role: str | None,
    settings: Settings | None = None,
) -> AuthenticatedCaller:
    settings = settings or get_settings()
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if not x_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Role header",
        )
    try:
        role = Role(x_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown role: {x_role}",
        ) from exc

    allowed_keys = settings.role_api_keys().get(role.value, set())
    if x_api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED",
        )
    return AuthenticatedCaller(role=role, api_key_id=f"{role.value}:{x_api_key[:4]}***")


def require_roles(*allowed: Role):
    allowed_set = set(allowed)

    async def dependency(
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_role: str | None = Header(default=None, alias="X-Role"),
    ) -> AuthenticatedCaller:
        caller = resolve_caller(x_api_key, x_role)
        if caller.role not in allowed_set and caller.role != Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS_DENIED",
            )
        return caller

    return dependency
