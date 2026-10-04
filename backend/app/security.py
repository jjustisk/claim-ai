"""Shared security helpers: env mode, secret strength, rate limits, headers."""

from __future__ import annotations

import os
import re
import secrets
import time
from collections import defaultdict
from threading import Lock
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_WEAK_JWT_SECRETS = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "secret",
        "jwt-secret",
        "your-secret-key",
        "dev",
        "test",
        "password",
    }
)

_DEV_API_KEY_MARKERS = frozenset(
    {
        "dev-processor-key",
        "dev-rehydrator-key",
        "dev-claims-key",
        "dev-auditor-key",
        "dev-admin-key",
    }
)

# Precomputed bcrypt hash used only to equalize login timing when a user is missing.
_DUMMY_PASSWORD_HASH = (
    "$2b$12$R9h/cIPz0gi.URNNX3kh2OPST9/PgBkqquzi.Ss7KIUgO2t0jWMUW"
)


def app_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def is_production() -> bool:
    return app_env() in {"production", "prod"}


def secrets_source() -> str:
    """env | vault | auto (default)."""
    return (os.getenv("CLAIM_AI_SECRETS_SOURCE") or "auto").strip().lower()


def use_env_secrets(settings_database_url: str, settings_jwt_secret: str) -> bool:
    source = secrets_source()
    if source == "env":
        return True
    if source == "vault":
        return False
    from app.connectors.secrets import is_running_on_azure

    if is_running_on_azure():
        return False
    return bool(settings_database_url and settings_jwt_secret)


def validate_jwt_secret(secret: str) -> None:
    normalized = (secret or "").strip()
    if normalized.lower() in _WEAK_JWT_SECRETS or len(normalized) < 32:
        if is_production() or secrets_source() == "env":
            raise ValueError(
                "JWT_SECRET_KEY is missing or too weak. Use a random secret of at least "
                "32 characters (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)."
            )


def validate_database_url(database_url: str) -> None:
    """Require TLS to Postgres outside local/dev compose."""
    if not database_url:
        return
    if not (is_production() or secrets_source() == "env"):
        return
    parsed = urlparse(database_url.replace("postgresql+psycopg", "postgresql", 1))
    host = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "postgres", "db"}
    if host in local_hosts or host.endswith(".local"):
        return
    query = (parsed.query or "").lower()
    if (
        "sslmode=require" not in query
        and "sslmode=verify-full" not in query
        and "sslmode=verify-ca" not in query
    ):
        raise ValueError(
            "DATABASE_URL must use sslmode=require (or verify-ca/verify-full) for non-local hosts."
        )


def validate_cors_origins(cors_origins: str) -> None:
    origins = [o.strip() for o in (cors_origins or "").split(",") if o.strip()]
    if not origins:
        return
    if any(o == "*" for o in origins):
        raise ValueError(
            "CORS_ORIGINS must not include '*' when credentials are enabled."
        )
    for origin in origins:
        if not re.match(r"^https?://[^/\s]+$", origin):
            raise ValueError(
                f"Invalid CORS origin (must be absolute http(s) origin): {origin!r}"
            )


def has_dev_api_keys(*keys: str) -> bool:
    return any((key or "").strip() in _DEV_API_KEY_MARKERS for key in keys)


def cookie_secure() -> bool:
    explicit = os.getenv("COOKIE_SECURE")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return is_production()


def dummy_password_hash() -> str:
    return _DUMMY_PASSWORD_HASH


def trusted_hosts() -> list[str] | None:
    """Return TrustedHost allow-list, or None to disable the middleware."""
    raw = (os.getenv("TRUSTED_HOSTS") or "").strip()
    if raw == "*":
        return None
    if raw:
        return [h.strip() for h in raw.split(",") if h.strip()]
    if is_production():
        return ["localhost", "127.0.0.1", "backend", "frontend"]
    return None


class LoginRateLimiter:
    """Simple in-memory login throttle (per process)."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded and request.client:
            return forwarded.split(",")[0].strip() or request.client.host
        return request.client.host if request.client else "unknown"

    def _key(self, request: Request, username: str) -> str:
        return f"{self._client_ip(request)}:{username.strip().lower()}"

    def check(self, request: Request, username: str) -> bool:
        now = time.monotonic()
        key = self._key(request, username)
        with self._lock:
            stamps = [t for t in self._attempts[key] if now - t < self.window_seconds]
            self._attempts[key] = stamps
            return len(stamps) < self.max_attempts

    def record_failure(self, request: Request, username: str) -> None:
        key = self._key(request, username)
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def reset(self, request: Request, username: str) -> None:
        key = self._key(request, username)
        with self._lock:
            self._attempts.pop(key, None)

    def retry_after_seconds(self) -> int:
        return self.window_seconds


login_rate_limiter = LoginRateLimiter()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault("X-XSS-Protection", "0")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if is_production():
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        if "server" in response.headers:
            del response.headers["server"]
        return response


def generate_jwt_secret() -> str:
    return secrets.token_urlsafe(48)
