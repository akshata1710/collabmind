import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.message import Message
from app.models.channel import Channel
from app.models.user import User
from app.core.redis_manager import manager
from app.schemas.schemas import MessageOut

router = APIRouter(tags=["websocket"])

# Track which channels already have a Redis subscriber running on this server
_subscribed_channels: set[int] = set()


@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: int,
    token: str = Query(...),
):
    # Step 1: Authenticate
    async with AsyncSessionLocal() as db:
        try:
            from jose import jwt as jose_jwt
            from app.core.config import settings
            payload = jose_jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            user_id = int(payload.get("sub"))
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                await websocket.close(code=4001)
                return
        except Exception:
            await websocket.close(code=4001)
            return

        channel = await db.get(Channel, channel_id)
        if not channel:
            await websocket.close(code=4004)
            return

    # Step 2: Accept WebSocket and update presence
    await manager.connect(websocket, channel_id)
    await manager.set_presence(user_id, "online")

    # Step 3: Start Redis subscriber for this channel if not already running
    subscriber_task = None
    if channel_id not in _subscribed_channels:
        _subscribed_channels.add(channel_id)
        subscriber_task = asyncio.create_task(
            manager.start_subscriber(channel_id)
        )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                content = data.get("content", "").strip()
                reply_to_id = data.get("reply_to_id")
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            if not content:
                continue

            # Step 4: Save message to DB
            async with AsyncSessionLocal() as db:
                message = Message(
                    content=content,
                    channel_id=channel_id,
                    author_id=user_id,
                    reply_to_id=reply_to_id,
                )
                db.add(message)
                await db.commit()

                result = await db.execute(
                    select(Message)
                    .where(Message.id == message.id)
                    .options(selectinload(Message.author))
                )
                saved = result.scalar_one()
                out = MessageOut.model_validate(saved)

            # Step 5: Publish to Redis — reaches ALL servers
            await manager.publish(channel_id, out.model_dump(mode="json"))

    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)
        await manager.set_presence(user_id, "offline")

        # Clean up subscriber task if no one left in this channel
        if manager.active_local_count(channel_id) == 0 and subscriber_task:
            subscriber_task.cancel()
            _subscribed_channels.discard(channel_id)