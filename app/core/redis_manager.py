import asyncio
import json
from redis.asyncio import Redis
from fastapi import WebSocket
from collections import defaultdict

from app.core.config import settings


class RedisConnectionManager:
    """
    Replaces the in-memory ConnectionManager from Week 2.

    How it works:
    - Every API server subscribes to Redis channel "chat:{channel_id}"
    - When a message arrives, this server PUBLISHES it to Redis
    - Redis instantly delivers it to ALL servers subscribed to that channel
    - Each server then broadcasts to its own local WebSocket connections

    Result: User A on Server 1 can reach User B on Server 2.
    This is horizontal scaling.
    """

    def __init__(self):
        self._redis: Redis | None = None
        # local websocket connections on THIS server instance only
        self._local: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect_redis(self):
        self._redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def disconnect_redis(self):
        if self._redis:
            await self._redis.aclose()

    async def connect(self, websocket: WebSocket, channel_id: int):
        await websocket.accept()
        self._local[channel_id].add(websocket)

    def disconnect(self, websocket: WebSocket, channel_id: int):
        self._local[channel_id].discard(websocket)
        if not self._local[channel_id]:
            del self._local[channel_id]

    async def publish(self, channel_id: int, payload: dict):
        """Publish a message to Redis — all servers will receive it."""
        await self._redis.publish(f"chat:{channel_id}", json.dumps(payload))

    async def broadcast_local(self, channel_id: int, payload: dict):
        """Send to all WebSocket clients connected to THIS server."""
        dead = set()
        for ws in self._local.get(channel_id, set()):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws, channel_id)

    async def start_subscriber(self, channel_id: int):
        """
        Listen on Redis for this channel and broadcast locally.
        Runs as a background task for the lifetime of the first
        WebSocket connection on this server for this channel.
        """
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"chat:{channel_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    payload = json.loads(message["data"])
                    await self.broadcast_local(channel_id, payload)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"chat:{channel_id}")

    # Presence helpers (Redis key with TTL)
    async def set_presence(self, user_id: int, status: str, ttl: int = 30):
        """Mark user online/away/busy. Key expires after ttl seconds."""
        await self._redis.setex(f"presence:{user_id}", ttl, status)

    async def get_presence(self, user_id: int) -> str:
        status = await self._redis.get(f"presence:{user_id}")
        return status or "offline"

    async def get_channel_presence(self, user_ids: list[int]) -> dict[int, str]:
        """Batch-fetch presence for a list of users."""
        pipe = self._redis.pipeline()
        for uid in user_ids:
            pipe.get(f"presence:{uid}")
        results = await pipe.execute()
        return {uid: (status or "offline") for uid, status in zip(user_ids, results)}

    def active_local_count(self, channel_id: int) -> int:
        return len(self._local.get(channel_id, set()))


manager = RedisConnectionManager()