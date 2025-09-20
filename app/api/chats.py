from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.sa import get_session
from app.models.auth_models import User
from app.models.chat_models import Chat, Message


router = APIRouter(prefix="/api/chats", tags=["chats"])


class ChatOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateChatRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


@router.post("/", response_model=ChatOut)
async def create_chat(
    payload: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatOut:
    name = payload.name or datetime.utcnow().strftime("Chat on %Y-%m-%d %H:%M")
    chat = Chat(user_id=current_user.id, name=name)
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    await session.commit()
    return ChatOut.model_validate(chat)


@router.get("/", response_model=list[ChatOut])
async def list_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatOut]:
    stmt = select(Chat).where(Chat.user_id == current_user.id).order_by(Chat.created_at.desc())
    res = await session.execute(stmt)
    chats = list(res.scalars().all())
    return [ChatOut.model_validate(c) for c in chats]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(
    chat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MessageOut]:
    # Ensure chat belongs to user
    chat = await session.get(Chat, chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    res = await session.execute(stmt)
    msgs = list(res.scalars().all())
    return [MessageOut.model_validate(m) for m in msgs]


class AddMessageRequest(BaseModel):
    role: str = Field(pattern=r"^(user|agent|system)$")
    content: str


@router.post("/{chat_id}/messages", response_model=MessageOut)
async def add_message(
    chat_id: uuid.UUID,
    payload: AddMessageRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageOut:
    chat = await session.get(Chat, chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    msg = Message(chat_id=chat_id, role=payload.role, content=payload.content)
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    await session.commit()
    return MessageOut.model_validate(msg)


class RenameChatRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.patch("/{chat_id}", response_model=ChatOut)
async def rename_chat(
    chat_id: uuid.UUID,
    payload: RenameChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatOut:
    chat = await session.get(Chat, chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.name = payload.name
    await session.flush()
    await session.refresh(chat)
    await session.commit()
    return ChatOut.model_validate(chat)
