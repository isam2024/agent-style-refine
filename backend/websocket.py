import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        # Maps session_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_to_session(self, session_id: str, event: str, data: dict = None):
        """Send a message to all connections for a session."""
        if session_id not in self.active_connections:
            return

        message = json.dumps({"event": event, "data": data})
        dead_connections = set()

        for connection in self.active_connections[session_id]:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[session_id].discard(conn)

    async def broadcast_progress(
        self,
        session_id: str,
        step: str,
        progress: int = None,
        message: str = None,
    ):
        """Broadcast a progress update."""
        await self.send_to_session(
            session_id,
            "progress",
            {
                "step": step,
                "progress": progress,
                "message": message,
            },
        )

    async def broadcast_error(self, session_id: str, error: str):
        """Broadcast an error."""
        await self.send_to_session(
            session_id,
            "error",
            {"error": error},
        )

    async def broadcast_complete(self, session_id: str, result: dict = None):
        """Broadcast completion."""
        await self.send_to_session(
            session_id,
            "complete",
            result,
        )


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket, session_id)
    try:
        while True:
            # Keep connection alive, wait for messages
            data = await websocket.receive_text()
            # Could handle client messages here if needed
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception:
        manager.disconnect(websocket, session_id)
