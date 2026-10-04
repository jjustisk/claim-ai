"""JSON auth API. Vue will call these; the test UI in pages/ is temporary."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.schemas.responses import CurrentUser, TokenResponse
from app.connectors.db import get_db
from app.security import login_rate_limiter
from app.services.auth_service import InvalidCredentials, authenticate, get_account_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    if not login_rate_limiter.check(request, form.username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Please try again later.",
            headers={"Retry-After": str(login_rate_limiter.retry_after_seconds())},
        )
    try:
        result = await authenticate(form.username, form.password, db)
    except InvalidCredentials:
        login_rate_limiter.record_failure(request, form.username)
        # Small delay to slow online guessing without blocking the event loop hard.
        await asyncio.sleep(0.25)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_rate_limiter.reset(request, form.username)
    return result


@router.get("/me", response_model=CurrentUser)
def me(user: dict = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser(**get_account_profile(user))
