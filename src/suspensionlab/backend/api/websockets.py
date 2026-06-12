from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging

from suspensionlab.backend.config import settings

logger = logging.getLogger(__name__)

# Basic in-memory fallback connection manager (for single-instance deployments)
# A robust multi-instance system would solely rely on Redis PubSub channels per session.
class ConnectionManager:
    def __init__(self):
        # Maps session_id to a list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"Client joined session {session_id}. Active: {len(self.active_connections[session_id])}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
            logger.info(f"Client left session {session_id}.")

    async def broadcast(self, message: dict, session_id: str):
        """Broadcast directly to local websockets (fallback mode)"""
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"WebSocket broadcast error: {e}")

manager = ConnectionManager()

# Optional: Redis Pub/Sub listener background task
async def redis_listener(session_id: str):
    import redis.asyncio as redis
    if not settings.redis_url:
        return
    try:
        redis_conn = redis.from_url(settings.redis_url)
        pubsub = redis_conn.pubsub()
        await pubsub.subscribe(f"session:{session_id}")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await manager.broadcast(data, session_id)
    except Exception as e:
        logger.error(f"Redis listener error for session {session_id}: {e}")

router = APIRouter(prefix="/ws", tags=["Websockets"])

@router.websocket("/sessions/{session_id}")
async def websocket_session_endpoint(websocket: WebSocket, session_id: str):
    """
    Real-time collaboration websocket.
    Requires authentication in production, usually via a short-lived ticket or cookie.
    """
    await manager.connect(websocket, session_id)
    
    # Ideally, trigger a background task for redis_listener here if not already running for this session.
    # We will simulate the pub-sub by accepting local messages and echoing them for now.
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Broadcast to everyone in the room
            # In a distributed system, we would publish to Redis here:
            # await redis_conn.publish(f"session:{session_id}", json.dumps(message))
            
            # Fallback to local broadcast
            await manager.broadcast(message, session_id)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
        await manager.broadcast({"event": "system", "message": "A user has left the session."}, session_id)
