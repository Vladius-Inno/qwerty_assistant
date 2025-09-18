from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.sa import get_session
from app.models.auth_models import RefreshToken, User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserProfile


router = APIRouter(tags=["auth"])
logger = logging.getLogger("app.auth")

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


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    # Check existing user
    res = await session.execute(select(User).where(User.email == payload.email))
    if res.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()  # to get user.id

    # Issue tokens
    access_token = create_access_token(user.id)
    # create a DB record for refresh token and include its UUID as jti in JWT
    refresh_row = RefreshToken(user_id=user.id, token="", expires_at=datetime.now(timezone.utc))
    session.add(refresh_row)
    await session.flush()
    refresh_token = create_refresh_token(user.id, jti=str(refresh_row.id))
    # update stored token and expiry from JWT claims
    claims = decode_token(refresh_token)
    refresh_row.token = refresh_token
    refresh_row.expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    await session.commit()
    logger.info(
        "User registered",
        extra={"event": "user_registered", "user_id": str(user.id), "email": user.email},
    )

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    res = await session.execute(select(User).where(User.email == payload.email))
    user = res.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.warning(
            "Login failed",
            extra={"event": "login_failed", "email": payload.email, "user_exists": user is not None},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        logger.warning(
            "Login blocked for inactive user",
            extra={"event": "login_inactive", "email": payload.email, "user_id": str(user.id)},
        )
        raise HTTPException(status_code=403, detail="User is inactive")

    access_token = create_access_token(user.id)

    refresh_row = RefreshToken(user_id=user.id, token="", expires_at=datetime.now(timezone.utc))
    session.add(refresh_row)
    await session.flush()
    refresh_token = create_refresh_token(user.id, jti=str(refresh_row.id))
    claims = decode_token(refresh_token)
    refresh_row.token = refresh_token
    refresh_row.expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    await session.commit()
    logger.info(
        "User login",
        extra={"event": "user_login", "user_id": str(user.id), "email": user.email},
    )

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            logger.warning(
                "Refresh token with invalid type",
                extra={"event": "refresh_token_invalid_type"},
            )
            raise HTTPException(status_code=401, detail="Invalid token type")
        sub = claims.get("sub")
        jti = claims.get("jti")
        if not sub or not jti:
            logger.warning(
                "Refresh token with missing claims",
                extra={"event": "refresh_token_missing_claims"},
            )
            raise HTTPException(status_code=401, detail="Invalid token claims")
        user_id = uuid.UUID(str(sub))
        token_id = uuid.UUID(str(jti))
    except JWTError:
        logger.warning(
            "Refresh token invalid or expired (JWT decode)",
            extra={"event": "refresh_token_decode_error"},
        )
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Validate token exists and is not revoked/expired
    res = await session.execute(
        select(RefreshToken).where(
            RefreshToken.id == token_id,
            RefreshToken.token == payload.refresh_token,
        )
    )
    token_row = res.scalar_one_or_none()
    if token_row is None or token_row.revoked:
        # Reuse detected or unknown token: proactively revoke all sessions for this user
        logger.warning(
            "Refresh token reuse detected; revoking all sessions",
            extra={
                "event": "refresh_reuse_detected",
                "user_id": str(user_id),
                "jti": str(token_id),
            },
        )
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
            .values(revoked=True)
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; all sessions revoked")
    if token_row.expires_at <= datetime.now(timezone.utc):
        logger.warning(
            "Refresh token expired",
            extra={"event": "refresh_token_expired", "user_id": str(user_id), "jti": str(token_id)},
        )
        raise HTTPException(status_code=401, detail="Refresh token expired")
    if token_row.user_id != user_id:
        logger.warning(
            "Refresh token user mismatch",
            extra={"event": "refresh_token_user_mismatch", "user_id": str(user_id), "jti": str(token_id)},
        )
        raise HTTPException(status_code=401, detail="Token/user mismatch")

    # Rotate: revoke old, create new
    token_row.revoked = True
    await session.flush()

    access_token = create_access_token(user_id)
    new_row = RefreshToken(user_id=user_id, token="", expires_at=datetime.now(timezone.utc))
    session.add(new_row)
    await session.flush()
    new_refresh_token = create_refresh_token(user_id, jti=str(new_row.id))
    new_claims = decode_token(new_refresh_token)
    new_row.token = new_refresh_token
    new_row.expires_at = datetime.fromtimestamp(new_claims["exp"], tz=timezone.utc)
    await session.commit()
    logger.info(
        "Tokens refreshed",
        extra={
            "event": "token_refreshed",
            "user_id": str(user_id),
            "old_jti": str(token_id),
            "new_jti": str(new_row.id),
        },
    )

    return TokenPair(access_token=access_token, refresh_token=new_refresh_token)


@router.get("/me", response_model=UserProfile)
async def me(current_user: User = Depends(get_current_user)) -> UserProfile:
    return UserProfile(id=current_user.id, email=current_user.email, is_active=current_user.is_active)


@router.post("/logout", status_code=200)
async def logout(
    payload: RefreshRequest | None = None,
    all_sessions: bool = Query(False, description="Revoke all refresh tokens for current user"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    # Revoke specific refresh token (if provided) or all for the user
    if all_sessions or not payload:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == current_user.id, RefreshToken.revoked == False)  # noqa: E712
            .values(revoked=True)
        )
        await session.commit()
        logger.info(
            "Logout all sessions",
            extra={"event": "logout_all", "user_id": str(current_user.id)},
        )
        return {"revoked": "all"}

    # Revoke the provided refresh token if it belongs to the current user
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            logger.warning(
                "Logout with invalid token type",
                extra={"event": "logout_invalid_type"},
            )
            raise HTTPException(status_code=400, detail="Invalid token type for logout")
        sub = claims.get("sub")
        jti = claims.get("jti")
        if not sub or not jti:
            logger.warning(
                "Logout with missing claims",
                extra={"event": "logout_missing_claims"},
            )
            raise HTTPException(status_code=400, detail="Invalid refresh token claims")
        token_id = uuid.UUID(str(jti))
        token_user_id = uuid.UUID(str(sub))
    except JWTError:
        logger.warning(
            "Logout with malformed or expired refresh token",
            extra={"event": "logout_token_decode_error"},
        )
        raise HTTPException(status_code=400, detail="Malformed or expired refresh token")

    if token_user_id != current_user.id:
        logger.warning(
            "Logout token does not belong to user",
            extra={"event": "logout_token_user_mismatch", "user_id": str(current_user.id), "jti": str(token_id)},
        )
        raise HTTPException(status_code=403, detail="Cannot revoke token of another user")

    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token_id, RefreshToken.user_id == current_user.id)
        .values(revoked=True)
    )
    await session.commit()
    logger.info(
        "Logout single session",
        extra={"event": "logout_single", "user_id": str(current_user.id), "jti": str(token_id)},
    )
    return {"revoked": "single", "jti": str(token_id)}
