"""WebSocket endpoint for real-time project updates."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ws_manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time project updates.

    Clients connect to receive events like:
    - photo_styled: When a photo finishes style transfer
    - video_ready: When a video finishes generating
    - export_complete: When an export finishes
    """
    await connection_manager.connect(websocket, project_id)
    try:
        while True:
            # Keep connection alive, receive any messages (ping/pong)
            data = await websocket.receive_text()
            # Echo back for ping-pong keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, project_id)
    except Exception as e:
        logger.warning("WebSocket error for project %s: %s", project_id, e)
        connection_manager.disconnect(websocket, project_id)
