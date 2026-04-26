from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.channel import Channel
from app.models.user import User
from app.schemas.schemas import ChannelCreate, ChannelOut
from app.core.security import get_current_user

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post("/", response_model=ChannelOut, status_code=201)
async def create_channel(
    payload: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(select(Channel).where(Channel.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel name already exists")

    channel = Channel(name=payload.name, description=payload.description)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.get("/", response_model=list[ChannelOut])
async def list_channels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Channel).order_by(Channel.name))
    return result.scalars().all()


@router.get("/{channel_id}", response_model=ChannelOut)
async def get_channel(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel