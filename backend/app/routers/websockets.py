from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt
from app.database import SessionLocal
from app.core.websocket import websocket_manager
from app.config import settings
from app.models.all_models import User

router = APIRouter(prefix="/ws", tags=["Realtime WebSocket"])

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint for real-time synchronization.
    Requires authentication via 'token' query parameter.
    """
    if not token:
        print("[WebSocket] Missing authentication token.")
        # Reject connection
        await websocket.accept()
        await websocket.close(code=4008, reason="Missing token")
        return

    db = SessionLocal()
    try:
        # Decode and validate token
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            print("[WebSocket] Token payload missing 'sub'.")
            await websocket.accept()
            await websocket.close(code=4008, reason="Invalid token")
            return

        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            print("[WebSocket] User not found or inactive.")
            await websocket.accept()
            await websocket.close(code=4008, reason="Unauthorized")
            return

        tenant_id = str(user.tenant_id)
    except Exception as e:
        print(f"[WebSocket] Authentication exception: {e}")
        await websocket.accept()
        await websocket.close(code=4008, reason="Authentication failed")
        return
    finally:
        db.close()

    await websocket_manager.connect(tenant_id, websocket)
    try:
        # Keep connection open and handle incoming messages/pings
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        websocket_manager.disconnect(tenant_id, websocket)
    except Exception as e:
        print(f"[WebSocket] Disconnect due to exception: {e}")
        websocket_manager.disconnect(tenant_id, websocket)
