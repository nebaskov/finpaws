from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlmodel import col

from app.api.models import UserRow
from app.auth.security import decode_token, hash_password, issue_token, verify_password

#: A FastAPI dependency that yields a short-lived SQLAlchemy session.
SessionProvider = Callable[[], Iterator[Session]]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    user_id: str
    email: str
    display_name: str


bearer_scheme = HTTPBearer(auto_error=False)


def make_router(get_session: SessionProvider) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", response_model=TokenOut, status_code=201)
    def register(payload: RegisterIn, session: Session = Depends(get_session)) -> TokenOut:
        existing = session.execute(
            select(UserRow).where(col(UserRow.email) == payload.email)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="email already registered")
        user = UserRow(
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        session.add(user)
        try:
            session.commit()
            session.refresh(user)
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=500, detail="registration failed") from exc
        return TokenOut(access_token=issue_token(user.id, user.email))

    @router.post("/login", response_model=TokenOut)
    def login(payload: LoginIn, session: Session = Depends(get_session)) -> TokenOut:
        user = session.execute(
            select(UserRow).where(col(UserRow.email) == payload.email)
        ).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid credentials")
        return TokenOut(access_token=issue_token(user.id, user.email))

    return router


def make_current_user_dep(get_session: SessionProvider) -> Callable[..., MeOut]:
    def current_user(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        session: Session = Depends(get_session),
    ) -> MeOut:
        if creds is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
        try:
            payload = decode_token(creds.credentials)
        except (PyJWTError, ValidationError) as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc

        user = session.get(UserRow, payload.sub)
        if user is None:
            raise HTTPException(status_code=401, detail="user not found")
        return MeOut(user_id=user.id, email=user.email, display_name=user.display_name)

    return current_user
