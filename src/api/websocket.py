"""WebSocket handler: real-time video and metrics streaming."""

import logging
import asyncio
import json
import base64
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import cv2 as cv

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")
    
    async def send(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Send error: {e}")


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint: video frames + metrics."""
    await manager.connect(websocket)
    
    from .main import get_system_state
    state = get_system_state()
    
    # Send connection confirmation
    await manager.send({
        "type": "connected",
        "message": "WebSocket ready"
    }, websocket)
    
    # Start streaming tasks
    frame_task = asyncio.create_task(stream_frames(websocket, state))
    metrics_task = asyncio.create_task(stream_metrics(websocket, state))
    
    try:
        while True:
            # Listen for client messages (keep connection alive)
            data = await websocket.receive_text()
            logger.debug(f"Received: {data}")
            
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        frame_task.cancel()
        metrics_task.cancel()
        manager.disconnect(websocket)


async def stream_frames(websocket: WebSocket, state: dict):
    """Stream video frames at 10 FPS."""
    vision = state['vision_processor']
    
    while True:
        try:
            if not vision:
                await asyncio.sleep(1)
                continue
            
            success, frame = vision.capture_frame()
            
            if success and frame is not None:
                # Encode as JPEG
                _, buffer = cv.imencode('.jpg', frame, [cv.IMWRITE_JPEG_QUALITY, 70])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                await manager.send({
                    "type": "frame",
                    "image": frame_base64
                }, websocket)
            
            await asyncio.sleep(0.1)  # 10 FPS
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Frame streaming error: {e}")
            await asyncio.sleep(1)


async def stream_metrics(websocket: WebSocket, state: dict):
    """Stream metrics at 1 Hz."""
    while True:
        try:
            metrics = state['current_metrics']
            
            await manager.send({
                "type": "metrics",
                "data": metrics
            }, websocket)
            
            await asyncio.sleep(1.0)  # 1 Hz
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Metrics streaming error: {e}")
            await asyncio.sleep(1)
