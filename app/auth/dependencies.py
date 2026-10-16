
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.database import get_db
from app.models.entities import Agent, Customer


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        role = payload.get("role")

        if not isinstance(subject, str) or ":" not in subject:
            raise credentials_error

        account_type, account_id = subject.split(":", 1)
        user_id = int(account_id)

    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_error

    if account_type == "customer" and role == "Customer":
        result = await db.execute(
            select(Customer).where(Customer.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise credentials_error

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "account_type": "customer",
            "role": "Customer",
        }

    if account_type == "agent" and role in ("Agent", "Admin"):
        result = await db.execute(
            select(Agent).where(Agent.id == user_id)
        )
        user = result.scalar_one_or_none()

        if (
            user is None
            or not user.is_active
            or user.role != role
        ):
            raise credentials_error

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "account_type": "agent",
            "role": user.role,
        }

    raise credentials_error


def require_roles(*allowed_roles: str):
    async def role_checker(
        current_user=Depends(get_current_user),
    ):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )

        return current_user

    return role_checker
