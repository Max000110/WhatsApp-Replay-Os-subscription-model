import json
import asyncio
import time
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt
from sqlalchemy import text
from app.database import SessionLocal
from app.core.websocket import websocket_manager
from app.config import settings
from app.models.all_models import User, Chatbot, Conversation, Message
from app.services.session_service import session_service

router = APIRouter(prefix="/ws", tags=["Realtime WebSocket"])

# Initialize redis client
redis_client = aioredis.from_url(settings.REDIS_URL)

class AgentConnectionManager:
    async def connect(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        print(f"[AgentWS] Agent connected: {agent_id}")

    def disconnect(self, websocket: WebSocket, agent_id: str):
        print(f"[AgentWS] Agent disconnected: {agent_id}")

manager = AgentConnectionManager()

async def listen_whatsapp_outbound():
    """
    Subscribes to 'whatsapp_outbound' channel, retrieves session info from DB,
    and dispatches outbound messages via session_service.send_whatsapp_message.
    """
    print("[WebSocket Router] Initializing Redis pubsub listener task...")
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe("whatsapp_outbound")
        print("[WebSocket Router] Subscribed to Redis channel: whatsapp_outbound")
    except Exception as subscribe_err:
        print(f"[WebSocket Router] [CRITICAL_FAULT] Redis subscription failed: {subscribe_err}")
        return

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    to_jid = payload.get("to_jid") or payload.get("jid")
                    text_msg = payload.get("text")
                    tenant_id = payload.get("tenant_id")
                    
                    if not to_jid or not text_msg or not tenant_id:
                        print(f"[whatsapp_outbound] Validation Error - Missing fields in payload: {payload}")
                        continue
                    
                    # Clean phone number from JID (e.g. 917021886525@s.whatsapp.net -> 917021886525)
                    to_phone = to_jid.split("@")[0]
                    
                    db = SessionLocal()
                    try:
                        # 1. Fetch active chatbot session_id for tenant
                        bot = db.query(Chatbot).filter(
                            Chatbot.tenant_id == tenant_id,
                            Chatbot.is_active == True
                        ).first()
                        if not bot or not bot.session_id:
                            print(f"[whatsapp_outbound] No active session found for tenant {tenant_id}")
                            continue
                            
                        session_id = str(bot.session_id)
                        
                        # 2. Get or create conversation thread
                        conv = db.query(Conversation).filter(
                            Conversation.tenant_id == tenant_id,
                            Conversation.customer_phone == to_phone
                        ).first()
                        if not conv:
                            conv = Conversation(
                                tenant_id=tenant_id,
                                customer_phone=to_phone,
                                handoff_status="HUMAN_ACTIVE",
                                bot_override=True
                            )
                            db.add(conv)
                            db.commit()
                            db.refresh(conv)
                            
                        # 3. Create outbound message DB state
                        new_msg = Message(
                            conversation_id=conv.id,
                            content=text_msg,
                            direction="outbound",
                            sender_type="user",
                            status="sending",
                            tenant_id=tenant_id,
                            session_id=session_id
                        )
                        db.add(new_msg)
                        db.commit()
                        db.refresh(new_msg)
                        
                        # Send WhatsApp message
                        success = await session_service.send_whatsapp_message(
                            session_id=session_id,
                            to_phone=to_phone,
                            text=text_msg,
                            message_id=str(new_msg.id)
                        )
                        
                        delivery_status = "sent" if success else "failed"
                        if success:
                            new_msg.status = "sent"
                            new_msg.ack_state = "sent"
                        else:
                            new_msg.status = "failed"
                            new_msg.ack_state = "failed"
                        db.commit()
                        
                        # Logging criteria: tenant_id, jid, message_id, delivery_status
                        print(
                            f"[whatsapp_outbound] Dispatch Status Log - "
                            f"tenant_id={tenant_id}, jid={to_jid}, "
                            f"message_id={new_msg.id}, delivery_status={delivery_status}"
                        )
                        
                        # Notify UI via websockets
                        msg_data = {
                            "id": str(new_msg.id),
                            "conversation_id": str(conv.id),
                            "direction": new_msg.direction,
                            "sender_type": new_msg.sender_type,
                            "content": new_msg.content,
                            "status": new_msg.status,
                            "created_at": new_msg.created_at.isoformat() if new_msg.created_at else None
                        }
                        await websocket_manager.publish_event(str(tenant_id), "message", msg_data)
                    finally:
                        db.close()
                except json.JSONDecodeError as json_err:
                    print(f"[whatsapp_outbound] Failed to parse message JSON: {json_err}")
                except Exception as err:
                    print(f"[whatsapp_outbound] Error processing message: {err}")
    except asyncio.CancelledError:
        print("[whatsapp_outbound] Listener cancelled")
    except Exception as e:
        print(f"[whatsapp_outbound] Error in listener loop: {e}")
    finally:
        try:
            await pubsub.unsubscribe("whatsapp_outbound")
            await pubsub.close()
        except Exception:
            pass

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint for real-time synchronization.
    Requires authentication via 'token' query parameter.
    """
    if not token:
        print("[WebSocket] Missing authentication token.")
        await websocket.accept()
        await websocket.close(code=4008, reason="Missing token")
        return

    db = SessionLocal()
    try:
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
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        websocket_manager.disconnect(tenant_id, websocket)
    except Exception as e:
        print(f"[WebSocket] Disconnect due to exception: {e}")
        websocket_manager.disconnect(tenant_id, websocket)

@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_endpoint_double(websocket: WebSocket, agent_id: str):
    await manager.connect(websocket, agent_id)
    try:
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("action") == "send_override_message":
                    payload = data.get("payload")
                    if not payload or not isinstance(payload, dict):
                        print(f"[AgentWS] Missing payload dictionary for manual override agent_id={agent_id}")
                        continue
                    
                    jid = payload.get("jid")
                    text_msg = payload.get("text")
                    tenant_id = payload.get("tenant_id")
                    
                    if not jid or not text_msg or not tenant_id:
                        print(f"[AgentWS] Validation Error: Missing required fields in override payload: {payload}")
                        continue
                    
                    # Direct publish block mapping to the required outbound structure
                    outbound_payload = {
                        "type": "human_override",
                        "tenant_id": str(tenant_id),
                        "jid": str(jid),
                        "text": str(text_msg),
                        "timestamp": str(time.time())
                    }
                    
                    await redis_client.publish("whatsapp_outbound", json.dumps(outbound_payload))
                    print(f"[AgentWS] Published manual override: tenant_id={tenant_id}, jid={jid}")
            except json.JSONDecodeError as decode_err:
                print(f"[AgentWS] JSON Decode Failure for manual override message agent_id={agent_id}: {decode_err}")
            except Exception as e:
                print(f"[AgentWS] Error handling socket message: {e}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, agent_id)

@router.websocket("/agent/{agent_id}")
async def agent_websocket_endpoint(websocket: WebSocket, agent_id: str):
    await manager.connect(websocket, agent_id)
    try:
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("action") == "send_override_message":
                    payload = data.get("payload")
                    if not payload or not isinstance(payload, dict):
                        print(f"[AgentWS] Missing payload dictionary for manual override agent_id={agent_id}")
                        continue
                    
                    jid = payload.get("jid")
                    text_msg = payload.get("text")
                    tenant_id = payload.get("tenant_id")
                    
                    if not jid or not text_msg or not tenant_id:
                        print(f"[AgentWS] Validation Error: Missing required fields in override payload: {payload}")
                        continue
                    
                    # Direct publish block mapping to the required outbound structure
                    outbound_payload = {
                        "type": "human_override",
                        "tenant_id": str(tenant_id),
                        "jid": str(jid),
                        "text": str(text_msg),
                        "timestamp": str(time.time())
                    }
                    
                    await redis_client.publish("whatsapp_outbound", json.dumps(outbound_payload))
                    print(f"[AgentWS] Published manual override: tenant_id={tenant_id}, jid={jid}")
            except json.JSONDecodeError as decode_err:
                print(f"[AgentWS] JSON Decode Failure for manual override message agent_id={agent_id}: {decode_err}")
            except Exception as e:
                print(f"[AgentWS] Error handling socket message: {e}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, agent_id)
