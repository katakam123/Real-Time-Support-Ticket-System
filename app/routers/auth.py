
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.entities import Agent, Customer
from app.schemas.auth import (
    CustomerRegister,
    CustomerResponse,
    CurrentUserResponse,
    TokenResponse,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_customer(
    data: CustomerRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Check both account tables to prevent duplicate emails.
    customer_result = await db.execute(
        select(Customer).where(Customer.email == data.email)
    )
    agent_result = await db.execute(
        select(Agent).where(Agent.email == data.email)
    )

    if (
        customer_result.scalar_one_or_none() is not None
        or agent_result.scalar_one_or_none() is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    customer = Customer(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
    )

    try:
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    return customer


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Swagger's OAuth2 password form sends the email in "username".
    result = await db.execute(
        select(Customer).where(
            Customer.email == form_data.username
        )
    )
    customer = result.scalar_one_or_none()

    if customer is not None:
        if (
            not customer.is_active
            or not verify_password(
                form_data.password,
                customer.password_hash,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(
            subject=f"customer:{customer.id}",
            role="Customer",
        )
        return TokenResponse(access_token=token)

    result = await db.execute(
        select(Agent).where(Agent.email == form_data.username)
    )
    agent = result.scalar_one_or_none()

    if (
        agent is None
        or not agent.is_active
        or not verify_password(
            form_data.password,
            agent.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=f"agent:{agent.id}",
        role=agent.role,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user=Depends(get_current_user),
):
    return current_user
