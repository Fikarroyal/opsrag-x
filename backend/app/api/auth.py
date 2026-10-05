"""Account endpoints: register, login, logout, current user. Sessions are HttpOnly cookies (a Bearer token is also accepted for scripts)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import authenticate, get_db, get_settings_dep
from app.auth import SESSION_COOKIE, LoginThrottle, hash_password, make_token, verify_password
from app.config import Settings
from app.database.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
_throttle = LoginThrottle()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Format email tidak valid")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


def _out(u: User) -> UserOut:
    return UserOut(id=str(u.id), name=u.name, email=u.email, role=u.role)


def _set_cookie(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_token(str(user.id), settings),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/register", status_code=201, response_model=UserOut, summary="Create an account and sign in")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> Any:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Email sudah terdaftar")
    first = (db.scalar(select(func.count()).select_from(User).where(User.password_hash.is_not(None))) or 0) == 0
    user = User(email=body.email, name=body.name, role="admin" if first else "it_support", password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    _set_cookie(response, user, settings)
    return _out(user)


@router.post("/login", response_model=UserOut, summary="Sign in")
def login(
    body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)
) -> Any:
    email = body.email.strip().lower()
    key = f"{email}|{request.client.host if request.client else '-'}"
    if _throttle.blocked(key):
        raise HTTPException(429, "Terlalu banyak percobaan masuk. Coba lagi beberapa menit lagi.")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        _throttle.fail(key)
        raise HTTPException(401, "Email atau kata sandi salah")
    _throttle.reset(key)
    _set_cookie(response, user, settings)
    return _out(user)


@router.post("/logout", status_code=204, summary="Sign out")
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut, summary="Current user")
def me(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> Any:
    return _out(authenticate(request, db, settings))
