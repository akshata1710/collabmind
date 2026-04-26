from collections import defaultdict
from fastapi import WebSocket
import json


class ConnectionManager:
    """
    Keeps track of all active WebSocket connections.
    When a message arrives, broadcast it to every connected
    client in that channel.
    """

    def __init__(self):
        # { channel_id: {websocket1, websocket2, ...} }
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, channel_id: int):
        await websocket.accept()
        self._connections[channel_id].add(websocket)

    def disconnect(self, websocket: WebSocket, channel_id: int):
        self._connections[channel_id].discard(websocket)
        if not self._connections[channel_id]:
            del self._connections[channel_id]

    async def broadcast(self, channel_id: int, payload: dict):
        """Send a JSON message to every client in this channel."""
        dead = set()
        for ws in self._connections.get(channel_id, set()):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws, channel_id)

    def active_count(self, channel_id: int) -> int:
        return len(self._connections.get(channel_id, set()))


# One shared instance for the whole app
manager = ConnectionManager()