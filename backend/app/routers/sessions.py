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
async def unified_dispatch(session_id: str, to_phone: str, text: str, message_id: str = None, options: dict = None) -> bool:
    """
    Unified outbound message dispatcher.
    Routes to WhatsApp Engine anti-ban queue via session_service.
    Identical to the campaign worker and Live Override dispatch path.
    """
    return await session_service.send_whatsapp_message(session_id, to_phone, text, message_id, options)


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
    import time
    t_start = time.time()
    db = SessionLocal()
    try:
        ws_session = db.query(WhatsAppSession).filter(WhatsAppSession.id == session_id).first()
        if not ws_session:
            print(f"[Webhook] Ignored event for untracked session: {session_id}")
            return

        tenant_id = ws_session.tenant_id

        if event == "message":
            from app.core.jid import normalize_jid
            from app.models.all_models import TenantSetting
            t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
            country_code = t_settings.default_country_code if t_settings and t_settings.default_country_code else "91"
            raw_from = data_dict.get("rawRemoteJid") or data_dict.get("from", "")
            try:
                customer_phone = normalize_jid(raw_from, default_country_code=country_code)
            except ValueError as err:
                print(
                    f"[Webhook - {session_id}] Rejected inbound message with invalid JID source "
                    f"from='{raw_from}' rawRemoteJid='{data_dict.get('rawRemoteJid', '')}' "
                    f"rawParticipant='{data_dict.get('rawParticipant', '')}': {err}"
                )
                return
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
                Conversation.tenant_id == tenant_id,
                Conversation.customer_phone == customer_phone
            ).first()

            if not conv:
                try:
                    conv = Conversation(
                        tenant_id=tenant_id,
                        session_id=ws_session.id,
                        customer_phone=customer_phone,
                        customer_name=customer_name
                    )
                    db.add(conv)
                    db.commit()
                    db.refresh(conv)
                except Exception:
                    db.rollback()
                    conv = db.query(Conversation).filter(
                        Conversation.tenant_id == tenant_id,
                        Conversation.customer_phone == customer_phone
                    ).first()

            # 2. Persist the inbound customer message with duplicate check
            import uuid
            msg_uuid = None
            wmsg_id = data_dict.get("messageId")
            if wmsg_id:
                try:
                    msg_uuid = uuid.UUID(wmsg_id)
                except ValueError:
                    pass
                
                # Deduplication check to prevent duplicate key constraint violations
                existing_msg = db.query(Message).filter(Message.whatsapp_message_id == wmsg_id).first()
                if existing_msg:
                    print(f"[Webhook] Message with whatsappMessageId '{wmsg_id}' already exists. Skipping insertion.")
                    return

            inbound_msg = Message(
                conversation_id=conv.id,
                client_uuid=msg_uuid,
                tenant_id=tenant_id,
                session_id=ws_session.id,
                direction="inbound",
                origin="inbound",
                sender_type="customer",
                content=message_body,
                status="read",
                ack_state="read",
                whatsapp_message_id=wmsg_id
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
                "client_uuid": str(inbound_msg.client_uuid) if inbound_msg.client_uuid else None,
                "conversation_id": str(inbound_msg.conversation_id),
                "tenant_id": str(inbound_msg.tenant_id) if inbound_msg.tenant_id else None,
                "session_id": str(inbound_msg.session_id) if inbound_msg.session_id else None,
                "direction": inbound_msg.direction,
                "origin": inbound_msg.origin,
                "sender_type": inbound_msg.sender_type,
                "content": inbound_msg.content,
                "status": inbound_msg.status,
                "ack_state": inbound_msg.ack_state,
                "whatsapp_message_id": inbound_msg.whatsapp_message_id,
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

            # 3. Look for an active AI bot bound to this session (if not paused by agent or human handoff)
            from datetime import datetime, timezone
            is_paused = False
            bypass_reason = ""
            if conv.handoff_status in ["WAITING_AGENT", "HUMAN_ACTIVE"]:
                is_paused = True
                bypass_reason = f"handoff_status is {conv.handoff_status}"
            elif conv.bot_paused_until:
                now = datetime.now(timezone.utc)
                if conv.bot_paused_until > now:
                    is_paused = True
                    bypass_reason = f"bot paused until {conv.bot_paused_until}"
            
            bot = None
            if not is_paused:
                bot = db.query(Chatbot).filter(
                    Chatbot.session_id == ws_session.id,
                    Chatbot.is_active == True
                ).first()
            else:
                print(f"[Webhook - {session_id}] AI chatbot bypassed: Conversation {conv.id} ({bypass_reason})")

            if bot:
                print(f"[Webhook - {session_id}] Routing to Chatbot: {bot.name}")
                t_db = int((time.time() - t_start) * 1000)
                
                # Fetch RAG context if enabled
                t_rag_start = time.time()
                kb_context = ""
                if bot.rag_enabled:
                    kb_context = await rag_service.fetch_matching_context(db, ws_session.id, message_body)
                t_rag = int((time.time() - t_rag_start) * 1000)

                # 1. Intent Classifier & Specialized Agent Router (Phase 5 & 6)
                from app.services.ai_service import classify_intent
                detected_intent = classify_intent(message_body)
                
                # Persist the intent in conversation memory (Phase 7)
                conv.last_intent = detected_intent
                db.commit()
                db.refresh(conv)
                print(f"[Webhook - {session_id}] Intent Classify & Route: {detected_intent}")

                # Prompt Assembly
                t_prompt_start = time.time()
                from app.services.ai_service import assemble_layered_prompt
                injected_prompt = assemble_layered_prompt(bot, conv, kb_context, intent=detected_intent)
                t_prompt = int((time.time() - t_prompt_start) * 1000)

                # Capture necessary IDs to prevent using detached SQLAlchemy objects
                conv_id = conv.id
                ws_session_id = ws_session.id

                # Close database session to release connection to the pool during slow LLM inference!
                db.close()

                # Generate AI response via Ollama (or configured provider)
                t_model_start = time.time()
                db_fresh = SessionLocal()
                try:
                    reply = await ai_gateway.generate_response(
                        prompt=message_body,
                        system_prompt=injected_prompt,
                        model=bot.model_name,
                        db=db_fresh,
                        tenant_id=tenant_id,
                        chatbot_id=bot.id
                    )
                finally:
                    db_fresh.close()
                t_model = int((time.time() - t_model_start) * 1000)

                # Re-open session to persist outbound bot reply
                db = SessionLocal()
                try:
                    # 4. Persist outbound bot reply with queued ACK status
                    outbound_msg = Message(
                        conversation_id=conv_id,
                        tenant_id=tenant_id,
                        session_id=ws_session_id,
                        direction="outbound",
                        origin="outbound",
                        sender_type="bot",
                        content=reply,
                        status="queued",
                        ack_state="queued"
                    )
                    db.add(outbound_msg)
                    db.commit()
                    db.refresh(outbound_msg)

                    # Update conversation last activity
                    conv_db = db.query(Conversation).filter(Conversation.id == conv_id).first()
                    if conv_db:
                        conv_db.last_message_at = outbound_msg.created_at
                        db.commit()
                        db.refresh(conv_db)
                except Exception as db_err:
                    print(f"[Webhook - {session_id}] Failed to save outbound reply to DB:", db_err)
                    db.rollback()

                # Publish real-time events for bot reply
                outbound_msg_data = {
                    "id": str(outbound_msg.id),
                    "client_uuid": str(outbound_msg.client_uuid) if outbound_msg.client_uuid else None,
                    "conversation_id": str(outbound_msg.conversation_id),
                    "tenant_id": str(outbound_msg.tenant_id) if outbound_msg.tenant_id else None,
                    "session_id": str(outbound_msg.session_id) if outbound_msg.session_id else None,
                    "direction": outbound_msg.direction,
                    "origin": outbound_msg.origin,
                    "sender_type": outbound_msg.sender_type,
                    "content": outbound_msg.content,
                    "status": outbound_msg.status,
                    "ack_state": outbound_msg.ack_state,
                    "whatsapp_message_id": outbound_msg.whatsapp_message_id,
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
                t_delivery_start = time.time()
                from app.models.all_models import TenantSetting
                t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
                opts = {
                    "replyDelay": t_settings.reply_delay if t_settings else 2,
                    "simulateTypingDelay": t_settings.simulate_typing_delay if t_settings else 1000,
                    "sendMode": t_settings.send_mode if t_settings else "humanized"
                }
                success = await unified_dispatch(str(ws_session.id), customer_phone, reply, str(outbound_msg.id), opts)
                t_delivery = int((time.time() - t_delivery_start) * 1000)
                
                t_total = int((time.time() - t_start) * 1000)
                print(f"[Latency Profile] DB = {t_db} ms, RAG = {t_rag} ms, Prompt = {t_prompt} ms, Model = {t_model} ms, Delivery = {t_delivery} ms, Total = {t_total} ms")
                
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
            msg.ack_state = status
            if whatsapp_message_id:
                msg.whatsapp_message_id = whatsapp_message_id
            db.commit()
            db.refresh(msg)
            
            conv = msg.conversation
            tenant_id = conv.tenant_id
            
            # Publish real-time event to WebSockets
            message_data = {
                "id": str(msg.id),
                "client_uuid": str(msg.client_uuid) if msg.client_uuid else None,
                "conversation_id": str(msg.conversation_id),
                "tenant_id": str(msg.tenant_id) if msg.tenant_id else None,
                "session_id": str(msg.session_id) if msg.session_id else None,
                "direction": msg.direction,
                "origin": msg.origin,
                "sender_type": msg.sender_type,
                "content": msg.content,
                "status": msg.status,
                "ack_state": msg.ack_state,
                "whatsapp_message_id": msg.whatsapp_message_id,
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
        "rawRemoteJid": getattr(data, "rawRemoteJid", ""),
        "rawParticipant": getattr(data, "rawParticipant", ""),
        "timestamp": getattr(data, "timestamp", 0),
    }
    background_tasks.add_task(process_incoming_chat_pipeline, session_id, event, data_dict)
    return {"status": "queued"}
