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

    # 2. Persist the outbound agent message
    new_msg = Message(
        conversation_id=conv.id,
        direction="outbound",
        sender_type="user",
        content=payload.content,
        status="pending"
    )
    db.add(new_msg)
    db.commit()

    # 3. Request WhatsApp Engine to push message safely
    success = await session_service.send_whatsapp_message(sess.id, clean_phone, payload.content)
    if success:
        new_msg.status = "sent"
    else:
        new_msg.status = "failed"
        
    db.commit()
    db.refresh(new_msg)

    # Update conversation last activity stamp
    conv.last_message_at = new_msg.created_at
    db.commit()

    return new_msg
