from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.auth.service import get_current_tenant_id
from app.models.all_models import WhatsAppSession, Chatbot, Conversation, Message
from app.schemas.all_schemas import SessionCreate, SessionResponse, EngineWebhookPayload
from app.services.session_service import session_service
from app.services.rag_service import rag_service
from app.services.ai_service import ai_gateway
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
    existing_count = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant_id).count()
    if existing_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your subscription tier allows a maximum of 3 active WhatsApp sessions."
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
async def unified_dispatch(session_id: str, to_phone: str, text: str) -> bool:
    """
    Unified outbound message dispatcher.
    Routes to WhatsApp Engine anti-ban queue via session_service.
    Identical to the campaign worker and Live Override dispatch path.
    """
    return await session_service.send_whatsapp_message(session_id, to_phone, text)


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
                content=message_body
            )
            db.add(inbound_msg)
            db.commit()

            conv.last_message_at = inbound_msg.created_at
            db.commit()

            # 3. Look for an active AI bot bound to this session
            bot = db.query(Chatbot).filter(
                Chatbot.session_id == ws_session.id,
                Chatbot.is_active == True
            ).first()

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

                # 4. Persist outbound bot reply with pending ACK status
                outbound_msg = Message(
                    conversation_id=conv.id,
                    direction="outbound",
                    sender_type="bot",
                    content=reply,
                    status="pending"
                )
                db.add(outbound_msg)
                db.commit()

                # 5. ── UNIFIED DISPATCHER ──
                # Identical dispatch path to Live Override and Campaign worker
                success = await unified_dispatch(str(ws_session.id), customer_phone, reply)
                
                outbound_msg.status = "sent" if success else "failed"
                db.commit()
                
                if success:
                    print(f"[Webhook - {session_id}] AI reply queued for delivery to {customer_phone}")
                else:
                    print(f"[Webhook - {session_id}] AI reply dispatch FAILED for {customer_phone}")

    except Exception as err:
        print(f"[Webhook Pipeline - {session_id}] Unhandled error: {err}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        # Always close the session we opened — prevents connection pool exhaustion
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
            print(f"[Webhook] Session {session_id} state updated → {event}")
            return {"status": "state_updated"}

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
