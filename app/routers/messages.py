from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.message import Message
from app.models.channel import Channel
from app.models.user import User
from app.schemas.schemas import MessageCreate, MessageOut, ThreadOut
from app.core.security import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/", response_model=MessageOut, status_code=201)
async def send_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = await db.get(Channel, payload.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if payload.reply_to_id:
        parent = await db.get(Message, payload.reply_to_id)
        if not parent or parent.channel_id != payload.channel_id:
            raise HTTPException(status_code=400, detail="Invalid parent message")

    message = Message(
        content=payload.content,
        channel_id=payload.channel_id,
        author_id=current_user.id,
        reply_to_id=payload.reply_to_id,
    )
    db.add(message)
    await db.commit()

    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(selectinload(Message.author))
    )
    return result.scalar_one()


@router.get("/channel/{channel_id}", response_model=list[MessageOut])
async def list_messages(
    channel_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    result = await db.execute(
        select(Message)
        .where(Message.channel_id == channel_id, Message.reply_to_id.is_(None))
        .options(selectinload(Message.author))
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/thread/{message_id}", response_model=ThreadOut)
async def get_thread(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .where(Message.id == message_id)
        .options(selectinload(Message.author))
    )
    root = result.scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="Message not found")
    if root.reply_to_id is not None:
        raise HTTPException(status_code=400, detail="Use the root message id to fetch a thread")

    replies_result = await db.execute(
        select(Message)
        .where(Message.reply_to_id == message_id)
        .options(selectinload(Message.author))
        .order_by(Message.created_at.asc())
    )
    return ThreadOut(root=root, replies=replies_result.scalars().all())