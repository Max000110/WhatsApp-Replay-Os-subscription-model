from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Conversation, Message, WhatsAppSession
from app.schemas.all_schemas import ConversationResponse, MessageResponse, SendMessageRequest
from app.services.session_service import session_service
from uuid import UUID
from typing import List

router = APIRouter(prefix="/chats", tags=["Conversations & Live Chat"])

@router.get("/", response_model=List[ConversationResponse])
def list_conversations(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves all active customer chats for this tenant"""
    return db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id
    ).order_by(Conversation.last_message_at.desc()).all()

@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
def get_chat_history(conversation_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Fetches full historical message sequence for a customer channel"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation channel not found.")

    return db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

@router.post("/send", response_model=MessageResponse)
async def send_agent_message(payload: SendMessageRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Simulates agent manual overrides. Dispatches live support message, bypassing AI bots.
    """
    from app.routers.billing import has_exceeded_message_limit, is_subscription_active
    if not is_subscription_active(db, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your subscription plan has expired or is suspended. Please renew your plan to send messages."
        )

    if has_exceeded_message_limit(db, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your monthly outbound message limit has been reached. Please upgrade your subscription plan to send more."
        )

    # Verify session JID bounds
    sess = db.query(WhatsAppSession).filter(
        WhatsAppSession.id == payload.session_id,
        WhatsAppSession.tenant_id == tenant_id
    ).first()
    if not sess:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp session.")

    clean_phone = payload.to_phone.replace("+", "").replace(" ", "")

    # 1. Fetch or create conversation channels
    conv = db.query(Conversation).filter(
        Conversation.session_id == sess.id,
        Conversation.customer_phone == clean_phone
    ).first()
    if not conv:
        conv = Conversation(
            tenant_id=tenant_id,
            session_id=sess.id,
            customer_phone=clean_phone
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Set ownership takeover: pause AI bot for 15 minutes
    from datetime import datetime, timedelta, timezone
    conv.bot_paused_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    # 2. Persist the outbound agent message
    new_msg = Message(
        id=payload.client_uuid if payload.client_uuid else None,
        conversation_id=conv.id,
        direction="outbound",
        sender_type="user",
        content=payload.content,
        status="queued"
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)

    # Update conversation last activity stamp
    conv.last_message_at = new_msg.created_at
    db.commit()
    db.refresh(conv)

    # 3. Publish real-time events over WebSockets
    from app.core.websocket import websocket_manager
    message_data = {
        "id": str(new_msg.id),
        "conversation_id": str(new_msg.conversation_id),
        "direction": new_msg.direction,
        "sender_type": new_msg.sender_type,
        "content": new_msg.content,
        "status": new_msg.status,
        "created_at": new_msg.created_at.isoformat() if new_msg.created_at else None
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
    
    # Broadcast to websocket connections
    import asyncio
    asyncio.create_task(websocket_manager.publish_event(str(tenant_id), "message", message_data))
    asyncio.create_task(websocket_manager.publish_event(str(tenant_id), "conversation", conv_data))

    # 4. Request WhatsApp Engine to push message safely in the background
    asyncio.create_task(session_service.send_whatsapp_message(
        session_id=str(sess.id),
        to_phone=clean_phone,
        text=payload.content,
        message_id=str(new_msg.id)
    ))

    return new_msg
