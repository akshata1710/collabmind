from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.message import Message
from app.models.user import User
from app.schemas.schemas import MessageOut
from app.core.security import get_current_user
from app.services.ai_copilot import summarize, suggest_replies, classify

router = APIRouter(prefix="/ai", tags=["ai copilot"])


class SummarizeRequest(BaseModel):
    thread_id: int


class ReplyRequest(BaseModel):
    message_id: int


class ClassifyRequest(BaseModel):
    message_id: int


@router.post("/summarize")
async def summarize_thread(
    payload: SummarizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    root_result = await db.execute(
        select(Message)
        .where(Message.id == payload.thread_id)
        .options(selectinload(Message.author))
    )
    root = root_result.scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="Thread not found")

    replies_result = await db.execute(
        select(Message)
        .where(Message.reply_to_id == payload.thread_id)
        .options(selectinload(Message.author))
        .order_by(Message.created_at.asc())
    )
    replies = replies_result.scalars().all()

    all_messages = [MessageOut.model_validate(root).model_dump()]
    all_messages += [MessageOut.model_validate(r).model_dump() for r in replies]

    if len(all_messages) < 2:
        raise HTTPException(
            status_code=400,
            detail="Thread needs at least 2 messages to summarize"
        )

    summary = await summarize(all_messages)
    return {
        "thread_id": payload.thread_id,
        "message_count": len(all_messages),
        "summary": summary,
    }


@router.post("/reply")
async def smart_reply(
    payload: ReplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .where(Message.id == payload.message_id)
        .options(selectinload(Message.author))
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    context_result = await db.execute(
        select(Message)
        .where(
            Message.channel_id == message.channel_id,
            Message.id < payload.message_id,
        )
        .options(selectinload(Message.author))
        .order_by(Message.created_at.desc())
        .limit(5)
    )
    context = context_result.scalars().all()
    context_dicts = [MessageOut.model_validate(m).model_dump() for m in reversed(context)]

    suggestions = await suggest_replies(message.content, context_dicts)
    return {
        "message_id": payload.message_id,
        "message": message.content,
        "suggestions": suggestions,
    }


@router.post("/classify")
async def classify_message(
    payload: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .where(Message.id == payload.message_id)
        .options(selectinload(Message.author))
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    classification = await classify(message.content)
    return {
        "message_id": payload.message_id,
        "content": message.content,
        "classification": classification,
    }