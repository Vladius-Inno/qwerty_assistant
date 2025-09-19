from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.sa import get_session
from app.models.auth_models import User


logger = logging.getLogger("app.auth.deps")
oauth2_scheme = HTTPBearer()


async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        raw_token = token.credentials
        payload = decode_token(raw_token)
        if payload.get("type") != "access":
            logger.warning(
                "Access token with invalid type",
                extra={"event": "access_token_invalid_type"},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        sub = payload.get("sub")
        if not sub:
            logger.warning(
                "Access token missing subject",
                extra={"event": "access_token_missing_sub"},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
        user_id = uuid.UUID(str(sub))
    except JWTError:
        logger.warning(
            "Access token invalid or expired",
            extra={"event": "access_token_invalid_or_expired"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user or not user.is_active:
        logger.warning(
            "User inactive or not found for token",
            extra={"event": "access_token_user_not_found", "user_id": str(user_id)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")
    return user

