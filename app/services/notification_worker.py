"""
Notification microservice — runs as a separate process.

Subscribes to ALL chat channels on Redis and logs every message.
In production this would: send push notifications, emails,
update unread counts, trigger webhooks, etc.

This is what makes CollabMind a true microservice architecture —
this process is completely separate from the API server.
"""
import asyncio
import json
from redis.asyncio import Redis
from app.core.config import settings


async def main():
    print("[notification-worker] starting...")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()

    # Subscribe to ALL chat channels using a pattern
    await pubsub.psubscribe("chat:*")
    print("[notification-worker] subscribed to chat:* — listening for messages")

    async for message in pubsub.listen():
        if message["type"] == "pmessage":
            channel_key = message["channel"]   # e.g. "chat:1"
            channel_id = channel_key.split(":")[1]
            payload = json.loads(message["data"])

            # In production: send push notification, email, etc.
            # For now: log it so you can see it working
            print(
                f"[notification-worker] "
                f"channel={channel_id} "
                f"author={payload.get('author', {}).get('username')} "
                f"content={payload.get('content', '')[:60]}"
            )


if __name__ == "__main__":
    asyncio.run(main())