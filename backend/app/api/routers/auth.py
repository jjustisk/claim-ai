"""JSON auth API. Vue will call these; the test UI in pages/ is temporary."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.schemas.responses import CurrentUser, TokenResponse
from app.connectors.db import get_db
from app.services.auth_service import InvalidCredentials, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await authenticate(form.username, form.password, db)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )


@router.get("/me", response_model=CurrentUser)
def me(user: dict = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser(
        id=int(user["sub"]),
        role=str(user["role"]),
        email=str(user["email"]),
    )
