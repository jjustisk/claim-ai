"""Login, passwords, and JWT tokens.

Used by the JSON API login route (what Vue will call). Hash or check
passwords here, and create or decode access tokens. Do not put
claim-submit or review rules in this file.
"""

from datetime import datetime, timedelta

import bcrypt
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Assessor, Customer
from app.config import settings


class InvalidCredentials(Exception):
    """Raised when login email or password is incorrect."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


async def authenticate(email: str, password: str, db: AsyncSession) -> dict:
    result = await db.execute(select(Assessor).where(Assessor.email == email))
    assessor = result.scalar_one_or_none()
    if assessor and verify_password(password, assessor.hashed_password):
        token = create_access_token(
            {"sub": str(assessor.assessor_id), "role": "assessor", "email": assessor.email}
        )
        return {"access_token": token, "token_type": "bearer"}

    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()
    if customer and verify_password(password, customer.hashed_password):
        token = create_access_token(
            {"sub": str(customer.customer_id), "role": "claimant", "email": customer.email}
        )
        return {"access_token": token, "token_type": "bearer"}

    raise InvalidCredentials


def session_from_token(token: str) -> dict | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    role = payload.get("role")
    if role not in {"assessor", "claimant"}:
        return None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        return None
    return {
        "id": user_id,
        "role": role,
        "email": str(payload.get("email") or ""),
    }
