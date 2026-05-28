from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, SessionLocal
from app.auth.service import get_current_tenant_id
from app.models.all_models import WhatsAppSession, Chatbot, Conversation, Message, CampaignLog, Subscription
from app.schemas.all_schemas import SessionCreate, SessionResponse, EngineWebhookPayload
from app.services.session_service import session_service
from app.services.rag_service import rag_service
from app.services.ai_service import ai_gateway
from app.core.websocket import websocket_manager, publish_tenant_event_sync
from uuid import UUID
from typing import List

router = APIRouter(prefix="/sessions", tags=["WhatsApp Sessions"])

@router.get("/", response_model=List[SessionResponse])
def list_sessions(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Lists all WhatsApp sessions registered under the active tenant organisation space.
    """
    return db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant_id).all()

@router.post("/", response_model=SessionResponse)
async def create_session(payload: SessionCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Creates a new session record and commands the WhatsApp Engine container to initialize connection.
    """
    from app.routers.billing import is_subscription_active
    if not is_subscription_active(db, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your subscription plan has expired or is suspended. Please renew your plan to create new sessions."
        )

    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    max_bots = sub.max_bots if sub else 1 # Default to Free tier limit of 1

    existing_count = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant_id).count()
    if existing_count >= max_bots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Your subscription tier allows a maximum of {max_bots} active WhatsApp session(s). Upgrade your plan to add more."
        )

    new_session = WhatsAppSession(
        tenant_id=tenant_id,
        session_name=payload.session_name,
        status="disconnected"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    success = await session_service.init_whatsapp_connection(new_session.id)
    if not success:
        print("[Router] Warning: Failed to command Baileys engine. System will self-retry on boot.")
        
    return new_session

@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Retrieves the status and current QR code stream for a specific session.
    """
    session = db.query(WhatsAppSession).filter(
        WhatsAppSession.id == session_id,
        WhatsAppSession.tenant_id == tenant_id
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp session not found."
        )
    return session

@router.delete("/{session_id}")
def delete_session(session_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Deletes the session record.
    """
    session = db.query(WhatsAppSession).filter(
        WhatsAppSession.id == session_id,
        WhatsAppSession.tenant_id == tenant_id
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp session not found."
        )
    
    db.delete(session)
    db.commit()
    return {"message": "WhatsApp session successfully removed."}


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED OUTBOUND DISPATCHER
# Single shared entry-point used by ALL three outbound paths:
#   1. Live Override → /chats/send → chats.py → session_service
#   2. AI Auto-replies → webhook → process_incoming_chat_pipeline → HERE
#   3. Campaigns → worker/tasks.py → session_service
# All paths converge on session_service.send_whatsapp_message() → WhatsApp engine
# ─────────────────────────────────────────────────────────────────────────────
async def unified_dispatch(session_id: str, to_phone: str, text: str, message_id: str = None) -> bool:
    """
    Unified outbound message dispatcher.
    Routes to WhatsApp Engine anti-ban queue via session_service.
    Identical to the campaign worker and Live Override dispatch path.
    """
    return await session_service.send_whatsapp_message(session_id, to_phone, text, message_id)


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND PIPELINE: Inbound → AI → Unified Dispatch
#
# CRITICAL FIX: This function previously received the request-scoped `db`
# session from FastAPI's `get_db()` dependency. That session is CLOSED by
# FastAPI immediately after `return {"status": "queued"}` — BEFORE this
# background task runs. Using a closed session caused silent DB errors and
# incomplete AI reply delivery.
#
# Fix: The background task now opens its own independent SessionLocal()
# connection and fully owns its lifecycle (open → use → close in finally).
# ─────────────────────────────────────────────────────────────────────────────
async def process_incoming_chat_pipeline(session_id: str, event: str, data_dict: dict):
    """
    Background task with own DB session lifecycle.
    Inbound message → AI pipeline → unified_dispatch → WhatsApp delivery.
    """
    db = SessionLocal()
    try:
        ws_session = db.query(WhatsAppSession).filter(WhatsAppSession.id == session_id).first()
        if not ws_session:
            print(f"[Webhook] Ignored event for untracked session: {session_id}")
            return

        tenant_id = ws_session.tenant_id

        if event == "message":
            customer_phone = data_dict.get("from", "")
            message_body = data_dict.get("body", "")
            customer_name = data_dict.get("pushName", "")

            # Guard: reject delivery receipts, reactions, and empty-body events
            # These arrive from WhatsApp as libsignal-encrypted frames Baileys can't
            # decrypt (Bad MAC), resulting in empty body strings forwarded to webhook.
            if not customer_phone or not message_body or not message_body.strip():
                print(f"[Webhook] Skipping empty-body event from '{customer_phone}' (delivery receipt/reaction/Bad MAC)")
                return

            # 1. Fetch or create conversation record for this customer
            conv = db.query(Conversation).filter(
                Conversation.session_id == ws_session.id,
                Conversation.customer_phone == customer_phone
            ).first()

            if not conv:
                conv = Conversation(
                    tenant_id=tenant_id,
                    session_id=ws_session.id,
                    customer_phone=customer_phone,
                    customer_name=customer_name
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)

            # 2. Persist the inbound customer message
            inbound_msg = Message(
                conversation_id=conv.id,
                direction="inbound",
                sender_type="customer",
                content=message_body,
                status="read"
            )
            db.add(inbound_msg)
            db.commit()
            db.refresh(inbound_msg)

            conv.last_message_at = inbound_msg.created_at
            db.commit()
            db.refresh(conv)

            # Publish real-time events for inbound message
            inbound_msg_data = {
                "id": str(inbound_msg.id),
                "conversation_id": str(inbound_msg.conversation_id),
                "direction": inbound_msg.direction,
                "sender_type": inbound_msg.sender_type,
                "content": inbound_msg.content,
                "status": inbound_msg.status,
                "created_at": inbound_msg.created_at.isoformat() if inbound_msg.created_at else None
            }
            conv_data = {
                "id": str(conv.id),
                "tenant_id": str(conv.tenant_id),
                "session_id": str(conv.session_id),
                "customer_phone": conv.customer_phone,
                "customer_name": conv.customer_name,
                "is_archived": conv.is_archived,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
            }
            publish_tenant_event_sync(str(tenant_id), "message", inbound_msg_data)
            publish_tenant_event_sync(str(tenant_id), "conversation", conv_data)

            # Check monthly message limit
            from app.routers.billing import has_exceeded_message_limit, is_subscription_active
            if not is_subscription_active(db, tenant_id):
                print(f"[Webhook - {session_id}] AI reply bypassed: subscription plan expired or suspended for tenant {tenant_id}")
                return

            if has_exceeded_message_limit(db, tenant_id):
                print(f"[Webhook - {session_id}] AI reply bypassed: monthly message limit reached for tenant {tenant_id}")
                return

            # 3. Look for an active AI bot bound to this session (if not paused by agent)
            from datetime import datetime, timezone
            is_paused = False
            if conv.bot_paused_until:
                now = datetime.now(timezone.utc)
                if conv.bot_paused_until > now:
                    is_paused = True
            
            bot = None
            if not is_paused:
                bot = db.query(Chatbot).filter(
                    Chatbot.session_id == ws_session.id,
                    Chatbot.is_active == True
                ).first()
            else:
                print(f"[Webhook - {session_id}] AI chatbot bypassed: Conversation {conv.id} is owned by an agent (bot paused until {conv.bot_paused_until})")

            if bot:
                print(f"[Webhook - {session_id}] Routing to Chatbot: {bot.name}")
                
                # Fetch RAG context if enabled
                kb_context = ""
                if bot.rag_enabled:
                    kb_context = await rag_service.fetch_matching_context(db, ws_session.id, message_body)

                injected_prompt = bot.system_prompt
                if kb_context:
                    injected_prompt += f"\n\nUse the following verified facts to answer the customer request:\n{kb_context}\n\nImportant: If the info is not in the context, politely let the customer know."

                # Generate AI response via Ollama (or configured provider)
                reply = await ai_gateway.generate_response(
                    prompt=message_body,
                    system_prompt=injected_prompt,
                    model=bot.model_name,
                    db=db,
                    tenant_id=tenant_id,
                    chatbot_id=bot.id
                )

                # 4. Persist outbound bot reply with queued ACK status
                outbound_msg = Message(
                    conversation_id=conv.id,
                    direction="outbound",
                    sender_type="bot",
                    content=reply,
                    status="queued"
                )
                db.add(outbound_msg)
                db.commit()
                db.refresh(outbound_msg)

                # Update conversation last activity
                conv.last_message_at = outbound_msg.created_at
                db.commit()
                db.refresh(conv)

                # Publish real-time events for bot reply
                outbound_msg_data = {
                    "id": str(outbound_msg.id),
                    "conversation_id": str(outbound_msg.conversation_id),
                    "direction": outbound_msg.direction,
                    "sender_type": outbound_msg.sender_type,
                    "content": outbound_msg.content,
                    "status": outbound_msg.status,
                    "created_at": outbound_msg.created_at.isoformat() if outbound_msg.created_at else None
                }
                conv_data = {
                    "id": str(conv.id),
                    "tenant_id": str(conv.tenant_id),
                    "session_id": str(conv.session_id),
                    "customer_phone": conv.customer_phone,
                    "customer_name": conv.customer_name,
                    "is_archived": conv.is_archived,
                    "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
                }
                publish_tenant_event_sync(str(tenant_id), "message", outbound_msg_data)
                publish_tenant_event_sync(str(tenant_id), "conversation", conv_data)

                # 5. ── UNIFIED DISPATCHER ──
                success = await unified_dispatch(str(ws_session.id), customer_phone, reply, str(outbound_msg.id))
                
                if not success:
                    outbound_msg.status = "failed"
                    db.commit()
                    db.refresh(outbound_msg)
                    # Update status and broadcast failure
                    outbound_msg_data["status"] = "failed"
                    publish_tenant_event_sync(str(tenant_id), "message_status", outbound_msg_data)
                    print(f"[Webhook - {session_id}] AI reply dispatch FAILED for {customer_phone}")
                else:
                    print(f"[Webhook - {session_id}] AI reply queued for delivery to {customer_phone}")

    except Exception as err:
        print(f"[Webhook Pipeline - {session_id}] Unhandled error: {err}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        # Always close the session we opened — prevents connection pool exhaustion
        db.close()


async def process_ack_webhook(session_id: str, data_dict: dict):
    """
    Asynchronous background task to process message acknowledgement updates.
    Updates the database status for either standard Messages or CampaignLogs,
    and broadcasts real-time updates via WebSockets.
    """
    db = SessionLocal()
    try:
        message_id = data_dict.get("messageId")
        whatsapp_message_id = data_dict.get("whatsappMessageId")
        status = data_dict.get("status")
        
        # 1. Try finding in standard Messages
        msg = None
        if message_id:
            msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg and whatsapp_message_id:
            msg = db.query(Message).filter(Message.whatsapp_message_id == whatsapp_message_id).first()

        if msg:
            msg.status = status
            if whatsapp_message_id:
                msg.whatsapp_message_id = whatsapp_message_id
            db.commit()
            db.refresh(msg)
            
            conv = msg.conversation
            tenant_id = conv.tenant_id
            
            # Publish real-time event to WebSockets
            message_data = {
                "id": str(msg.id),
                "conversation_id": str(msg.conversation_id),
                "direction": msg.direction,
                "sender_type": msg.sender_type,
                "content": msg.content,
                "status": msg.status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            conv_data = {
                "id": str(conv.id),
                "tenant_id": str(conv.tenant_id),
                "session_id": str(conv.session_id),
                "customer_phone": conv.customer_phone,
                "customer_name": conv.customer_name,
                "is_archived": conv.is_archived,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
            }
            publish_tenant_event_sync(str(tenant_id), "message_status", message_data)
            publish_tenant_event_sync(str(tenant_id), "conversation", conv_data)
            print(f"[ACK Webhook] Message {msg.id} status updated to {status}")
            return

        # 2. Try finding in Campaign Logs
        campaign_log = None
        if message_id:
            campaign_log = db.query(CampaignLog).filter(CampaignLog.id == message_id).first()
        if not campaign_log and whatsapp_message_id:
            campaign_log = db.query(CampaignLog).filter(CampaignLog.whatsapp_message_id == whatsapp_message_id).first()

        if campaign_log:
            campaign_log.status = status
            if whatsapp_message_id:
                campaign_log.whatsapp_message_id = whatsapp_message_id
            if status == "sent":
                campaign_log.sent_at = func.now()
            elif status == "delivered":
                campaign_log.delivered_at = func.now()
            elif status == "read":
                campaign_log.read_at = func.now()
            
            db.commit()
            db.refresh(campaign_log)

            campaign = campaign_log.campaign
            tenant_id = campaign.tenant_id

            # Broadcast campaign log status update to websocket
            campaign_data = {
                "id": str(campaign.id),
                "tenant_id": str(campaign.tenant_id),
                "session_id": str(campaign.session_id) if campaign.session_id else None,
                "name": campaign.name,
                "template_text": campaign.template_text,
                "scheduled_time": campaign.scheduled_time.isoformat() if campaign.scheduled_time else None,
                "status": campaign.status,
                "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
                "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None
            }
            publish_tenant_event_sync(str(tenant_id), "campaign_status", {
                "campaign": campaign_data,
                "log": {
                    "id": str(campaign_log.id),
                    "campaign_id": str(campaign_log.campaign_id),
                    "recipient_phone": campaign_log.recipient_phone,
                    "status": campaign_log.status,
                    "sent_at": campaign_log.sent_at.isoformat() if campaign_log.sent_at else None,
                    "delivered_at": campaign_log.delivered_at.isoformat() if campaign_log.delivered_at else None,
                    "read_at": campaign_log.read_at.isoformat() if campaign_log.read_at else None
                }
            })
            print(f"[ACK Webhook] Campaign log {campaign_log.id} status updated to {status}")
            
    except Exception as err:
        print(f"[ACK Webhook] Error updating ACK status: {err}")
    finally:
        db.close()


@router.post("/webhook")
async def receive_engine_webhook(
    payload: EngineWebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Internal webhook receiving connection status updates and message events from Node Engine.
    Synchronous state changes are committed immediately.
    Heavy pipelines (AI + dispatch) are delegated to a background task.
    """
    session_id = payload.sessionId
    event = payload.event
    data = payload.data

    # Fast path: synchronous connection state updates
    if event in ["qr", "connected", "disconnected"]:
        ws_session = db.query(WhatsAppSession).filter(WhatsAppSession.id == session_id).first()
        if ws_session:
            if event == "qr":
                ws_session.status = "scanning"
                ws_session.qr_code = data.qr
            elif event == "connected":
                ws_session.status = "connected"
                ws_session.qr_code = None
                ws_session.phone_number = data.phone
            elif event == "disconnected":
                ws_session.status = "disconnected"
                ws_session.qr_code = None
            db.commit()
            db.refresh(ws_session)
            
            # Broadcast the updated session to websockets
            session_data = {
                "id": str(ws_session.id),
                "tenant_id": str(ws_session.tenant_id),
                "phone_number": ws_session.phone_number,
                "session_name": ws_session.session_name,
                "status": ws_session.status,
                "qr_code": ws_session.qr_code,
                "reconnect_attempts": ws_session.reconnect_attempts,
                "created_at": ws_session.created_at.isoformat() if ws_session.created_at else None,
                "updated_at": ws_session.updated_at.isoformat() if ws_session.updated_at else None
            }
            publish_tenant_event_sync(str(ws_session.tenant_id), "session", session_data)
            print(f"[Webhook] Session {session_id} state updated → {event}")
            return {"status": "state_updated"}

    # Fast path: handle ACK status updates asynchronously
    if event == "ack":
        data_dict = {
            "messageId": getattr(data, "messageId", ""),
            "whatsappMessageId": getattr(data, "whatsappMessageId", ""),
            "status": getattr(data, "status", "")
        }
        background_tasks.add_task(process_ack_webhook, session_id, data_dict)
        return {"status": "ack_queued"}

    # ── CRITICAL FIX: serialize to primitives ONLY before handing to background ──
    # The `db` session from get_db() will be CLOSED the moment this function returns.
    # The background task must NOT receive `db` — it opens its own SessionLocal() instead.
    data_dict = {
        "from": getattr(data, "from_", ""),
        "body": getattr(data, "body", ""),
        "pushName": getattr(data, "pushName", ""),
        "messageId": getattr(data, "messageId", ""),
        "timestamp": getattr(data, "timestamp", 0),
    }
    background_tasks.add_task(process_incoming_chat_pipeline, session_id, event, data_dict)
    return {"status": "queued"}
