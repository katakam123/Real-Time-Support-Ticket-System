
import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections = defaultdict(dict)
        self.lock = asyncio.Lock()

    async def connect(
        self,
        ticket_id: int,
        websocket: WebSocket,
        user: dict,
    ):
        await websocket.accept()

        async with self.lock:
            self.connections[ticket_id][websocket] = user

    async def disconnect(
        self,
        ticket_id: int,
        websocket: WebSocket,
    ):
        async with self.lock:
            ticket_connections = self.connections.get(ticket_id)

            if ticket_connections is not None:
                ticket_connections.pop(websocket, None)

                if not ticket_connections:
                    self.connections.pop(ticket_id, None)

    async def broadcast(
        self,
        ticket_id: int,
        data: dict,
        internal: bool = False,
        exclude: WebSocket | None = None,
    ):
        async with self.lock:
            recipients = list(
                self.connections.get(ticket_id, {}).items()
            )

        dead_connections = []

        for websocket, user in recipients:
            if websocket is exclude:
                continue

            if internal and user["role"] == "Customer":
                continue

            try:
                await websocket.send_text(json.dumps(data))
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            await self.disconnect(ticket_id, websocket)


manager = ConnectionManager()
