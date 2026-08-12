from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schema import Customer, Assessor
from app.auth import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # try assessor first, then claimant
    result = await db.execute(select(Assessor).where(Assessor.email == form.username))
    assessor = result.scalar_one_or_none()
    if assessor and verify_password(form.password, assessor.hashed_password):
        token = create_access_token({"sub": str(assessor.assessor_id), "role": "assessor", "email": assessor.email})
        return {"access_token": token, "token_type": "bearer"}

    result = await db.execute(select(Customer).where(Customer.email == form.username))
    customer = result.scalar_one_or_none()
    if customer and verify_password(form.password, customer.hashed_password):
        token = create_access_token({"sub": str(customer.customer_id), "role": "claimant", "email": customer.email})
        return {"access_token": token, "token_type": "bearer"}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")