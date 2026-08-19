from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.services.auth_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload  # contains sub (id), role, email


def require_assessor(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "assessor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assessor access required")
    return user


def require_claimant(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "claimant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Claimant access required")
    return user
