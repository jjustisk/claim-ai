"""Cookie session helpers for temporary HTML test pages."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.services.auth_service import session_from_token

COOKIE_TOKEN = "claim_ai_token"
COOKIE_EMAIL = "claim_ai_email"


def home_path_for_role(role: str) -> str:
    return "/ui/dashboard" if role == "assessor" else "/ui/home"


def session_from_request(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_TOKEN)
    email = request.cookies.get(COOKIE_EMAIL)
    if not token or not email:
        return None
    session = session_from_token(token)
    if session is None:
        return None
    session["token"] = token
    session["email"] = email
    return session


def require_ui_role(request: Request, role: str) -> dict | RedirectResponse:
    session = session_from_request(request)
    if not session:
        return RedirectResponse("/ui/login", status_code=303)
    if session["role"] != role:
        return RedirectResponse(home_path_for_role(session["role"]), status_code=303)
    return session
