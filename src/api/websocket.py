"""WebSocket handler: real-time video and metrics streaming."""

import logging
import asyncio
import json
import base64
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import cv2 as cv

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.video_modes: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.video_modes[websocket] = "annotated"
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.video_modes.pop(websocket, None)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    def set_video_mode(self, websocket: WebSocket, mode: str):
        if mode in {"annotated", "raw"}:
            self.video_modes[websocket] = mode

    def get_video_mode(self, websocket: WebSocket) -> str:
        return self.video_modes.get(websocket, "annotated")
    
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
    anomaly_task = asyncio.create_task(stream_anomaly(websocket, state))
    
    try:
        while True:
            # Listen for client messages (keep connection alive)
            data = await websocket.receive_text()
            logger.debug(f"Received: {data}")

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "control" and payload.get("action") == "video_annotations":
                mode = "annotated" if payload.get("showAnnotations", True) else "raw"
                manager.set_video_mode(websocket, mode)
                await manager.send({
                    "type": "control",
                    "action": "video_annotations",
                    "showAnnotations": mode == "annotated"
                }, websocket)
            
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        frame_task.cancel()
        metrics_task.cancel()
        anomaly_task.cancel()
        manager.disconnect(websocket)


async def stream_frames(websocket: WebSocket, state: dict):
    """Stream annotated video frames at 10 FPS with circular bubble boundaries."""
    vision = state['vision_processor']
    
    while True:
        try:
            if not vision:
                await asyncio.sleep(1)
                continue
            
            # Get annotated or raw frame based on the client's display mode
            frame_mode = manager.get_video_mode(websocket)
            frame = vision.get_annotated_frame() if frame_mode == "annotated" else vision.get_raw_frame()

            if frame is None and frame_mode == "raw":
                frame = vision.get_annotated_frame()
            
            if frame is not None:
                # Encode as JPEG (quality 70 for bandwidth efficiency)
                _, buffer = cv.imencode('.jpg', frame, [cv.IMWRITE_JPEG_QUALITY, 70])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                await manager.send({
                    "type": "frame",
                    "image": frame_base64,
                    "annotated": frame_mode == "annotated"
                }, websocket)
            
            await asyncio.sleep(0.2)  # 5 FPS matching processing rate
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Frame streaming error: {e}")
            await asyncio.sleep(1)


async def stream_metrics(websocket: WebSocket, state: dict):
    """Stream metrics at 5 FPS matching vision processing rate."""
    while True:
        try:
            metrics = state['current_metrics']
            
            await manager.send({
                "type": "metrics",
                "metrics": metrics
            }, websocket)
            
            await asyncio.sleep(0.2)  # 5 FPS (200ms) matching vision processing
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Metrics streaming error: {e}")
            await asyncio.sleep(1)


async def stream_anomaly(websocket: WebSocket, state: dict):
    """Stream anomaly status whenever a new anomaly state is produced."""
    last_sequence = None

    while True:
        try:
            anomaly = state.get('anomaly_status', {})
            sequence = anomaly.get('sequence')

            # Send initial status and then only updates.
            if last_sequence is None or sequence != last_sequence:
                await manager.send({
                    "type": "anomaly",
                    "status": anomaly.get('status', 'normal'),
                    "message": anomaly.get('message', ''),
                    "score": anomaly.get('score', 0.0),
                    "prediction": anomaly.get('prediction', 1),
                    "trained": anomaly.get('trained', False),
                    "timestamp": anomaly.get('timestamp', '')
                }, websocket)
                last_sequence = sequence

            await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Anomaly streaming error: {e}")
            await asyncio.sleep(1)
