
import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        # Key: (recipient_type, recipient_id)
        # Value: active WebSocket connections for that user
        self.connections = defaultdict(set)
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_key: tuple):
        await websocket.accept()

        async with self.lock:
            self.connections[user_key].add(websocket)

    async def disconnect(self, websocket: WebSocket, user_key: tuple):
        async with self.lock:
            sockets = self.connections.get(user_key)

            if sockets:
                sockets.discard(websocket)

                if not sockets:
                    self.connections.pop(user_key, None)

    async def send_to_user(self, user_key: tuple, data: dict):
        async with self.lock:
            sockets = list(self.connections.get(user_key, set()))

        dead_sockets = []

        for websocket in sockets:
            try:
                await websocket.send_text(json.dumps(data, default=str))
            except Exception:
                dead_sockets.append(websocket)

        for websocket in dead_sockets:
            await self.disconnect(websocket, user_key)

    async def broadcast_roles(self, roles: list, data: dict):
        async with self.lock:
            targets = [
                (user_key, websocket)
                for user_key, sockets in self.connections.items()
                if user_key[0] in roles
                for websocket in list(sockets)
            ]

        dead_sockets = []

        for user_key, websocket in targets:
            try:
                await websocket.send_text(json.dumps(data, default=str))
            except Exception:
                dead_sockets.append((user_key, websocket))

        for user_key, websocket in dead_sockets:
            await self.disconnect(websocket, user_key)


notification_manager = NotificationConnectionManager()
