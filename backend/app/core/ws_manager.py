"""WebSocket connection manager for real-time updates."""

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by project ID."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str):
        """Accept a new WebSocket connection and add it to the project group."""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.debug("WebSocket connected for project %s", project_id)

    def disconnect(self, websocket: WebSocket, project_id: str):
        """Remove a WebSocket connection from the project group."""
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.debug("WebSocket disconnected for project %s", project_id)

    async def broadcast_to_project(self, project_id: str, event: str, data: dict[str, Any]):
        """Broadcast a message to all connections for a specific project."""
        if project_id not in self.active_connections:
            return

        message = {"event": event, "data": data}
        disconnected = []

        for connection in self.active_connections[project_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Failed to send WebSocket message: %s", e)
                disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.disconnect(conn, project_id)

    async def send_photo_styled(self, project_id: str, photo_id: str, styled_url: str):
        """Notify that a photo has been styled."""
        await self.broadcast_to_project(
            str(project_id),
            "photo_styled",
            {"photo_id": photo_id, "styled_url": styled_url},
        )

    async def send_video_ready(self, project_id: str, video_id: str, video_url: str):
        """Notify that a video is ready."""
        await self.broadcast_to_project(
            str(project_id),
            "video_ready",
            {"video_id": video_id, "video_url": video_url},
        )

    async def send_export_complete(self, project_id: str, export_id: str, file_url: str):
        """Notify that an export is complete."""
        await self.broadcast_to_project(
            str(project_id),
            "export_complete",
            {"export_id": export_id, "file_url": file_url},
        )


# Global connection manager instance
connection_manager = ConnectionManager()
