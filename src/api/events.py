"""FastAPI WebSocket Connection Manager.

Manages active websocket connections, allowing the Orchestrator and Agents
to broadcast real-time events to the connected frontend UI.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections and event broadcasting per session."""
    
    def __init__(self) -> None:
        # Maps session_id to a list of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept the WebSocket connection and store it."""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info("WebSocket connected for session=%s", session_id)

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove the WebSocket connection."""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info("WebSocket disconnected for session=%s", session_id)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Broadcast a JSON message to all clients subscribed to the session."""
        if session_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning("Failed to send WebSocket message: %s", e)
                    dead_connections.append(connection)
            
            # Clean up dead connections
            for dead in dead_connections:
                self.disconnect(dead, session_id)

# Global connection manager instance
manager = ConnectionManager()
