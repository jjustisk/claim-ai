"""Test auth routes (login + role-protected endpoints).

Requires the API to be running:
    uvicorn app.main:app --reload

Run from backend/:
    python scripts/test_auth.py

Optional env:
    API_BASE_URL=http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
QUIT_COMMANDS = {"q", "quit", "exit"}


def _base_url() -> str:
    return os.getenv("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _check_health(client: httpx.Client) -> bool:
    try:
        response = client.get("/health", timeout=5.0)
        response.raise_for_status()
        print(f"  API health: {response.json()}")
        return True
    except Exception as exc:
        print(f"  API not reachable at {_base_url()}: {exc}", file=sys.stderr)
        print("  Start the server first: uvicorn app.main:app --reload", file=sys.stderr)
        return False


def _login(client: httpx.Client, email: str, password: str) -> dict | None:
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        print(f"  Login failed ({response.status_code}): {response.text}", file=sys.stderr)
        return None

    payload = response.json()
    token = payload.get("access_token")
    if not token:
        print("  Login response missing access_token", file=sys.stderr)
        return None

    return payload


def _decode_role_hint(client: httpx.Client, token: str) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    if response.status_code != 200:
        return None
    return response.json().get("role")


def _test_role_routes(client: httpx.Client, token: str, role: str | None) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/auth/me", headers=headers)
    print(f"  GET /api/auth/me → {me.status_code}")
    if me.status_code != 200:
        print("  FAIL: token should access /api/auth/me", file=sys.stderr)
        return False
    body = me.json()
    print(f"    {body}")
    if role and body.get("role") != role:
        print(f"  FAIL: expected role {role}, got {body.get('role')}", file=sys.stderr)
        return False
    return True


def _run_login_flow(client: httpx.Client) -> bool:
    print()
    email = input("Email: ").strip()
    if email.lower() in QUIT_COMMANDS:
        return False

    password = input("Password: ").strip()
    if password.lower() in QUIT_COMMANDS:
        return False

    print()
    print("Testing POST /api/auth/login ...")
    payload = _login(client, email, password)
    if payload is None:
        return False

    token = payload["access_token"]
    print("  Login: OK")
    print(f"  token_type: {payload.get('token_type', 'bearer')}")
    print(f"  access_token: {token[:24]}...")

    role = _decode_role_hint(client, token)
    if role:
        print(f"  role: {role}")
    else:
        print("  role: unknown (protected routes did not accept token)", file=sys.stderr)
        return False

    print()
    print("Testing role-protected routes ...")
    return _test_role_routes(client, token, role)


def main() -> int:
    base_url = _base_url()
    print("Auth route test")
    print(f"  Base URL: {base_url}")
    print("  Endpoints: POST /api/auth/login, GET /api/auth/me")
    print("  Commands: quit")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        if not _check_health(client):
            return 1

        passed = False
        while True:
            print()
            if not _run_login_flow(client):
                break
            passed = True
            print()
            again = input("Test another login? [y/N]: ").strip().lower()
            if again not in {"y", "yes"}:
                break

    if passed:
        print("SUCCESS: auth routes responded as expected.")
        return 0

    print("No successful login test completed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
