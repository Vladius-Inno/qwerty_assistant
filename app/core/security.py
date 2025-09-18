from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import os as _os  # to access env directly if needed


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


# JWT Settings from env with sane defaults
JWT_SECRET_KEY = _os.getenv("JWT_SECRET_KEY", "dev-insecure-change-me")
JWT_ALGORITHM = _os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(_os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(_os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(subject: str | uuid.UUID, extra_claims: Optional[Dict[str, Any]] = None,
                        expires_minutes: Optional[int] = None) -> str:
    if isinstance(subject, uuid.UUID):
        subject = str(subject)
    to_encode: Dict[str, Any] = {"sub": subject, "type": "access"}
    if extra_claims:
        to_encode.update(extra_claims)
    expire = _utcnow() + timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(subject: str | uuid.UUID, jti: Optional[str] = None,
                         expires_days: Optional[int] = None) -> str:
    if isinstance(subject, uuid.UUID):
        subject = str(subject)
    if not jti:
        jti = str(uuid.uuid4())
    expire = _utcnow() + timedelta(days=expires_days or REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode: Dict[str, Any] = {"sub": subject, "type": "refresh", "jti": jti, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


class TokenError(Exception):
    pass

