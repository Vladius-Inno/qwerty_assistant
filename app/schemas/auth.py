from __future__ import annotations

import uuid
from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: uuid.UUID
    email: EmailStr
    is_active: bool

class LogoutResponse(BaseModel):
    revoked: Literal["all", "single"]
    jti: Optional[str] = None
