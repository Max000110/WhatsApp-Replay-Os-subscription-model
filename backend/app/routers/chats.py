from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Conversation, Message, WhatsAppSession
from app.schemas.all_schemas import ConversationResponse, MessageResponse, SendMessageRequest, ConversationUpdate, HandoffStatusUpdate
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

    from app.core.jid import normalize_jid
    from app.models.all_models import TenantSetting
    t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
    country_code = t_settings.default_country_code if t_settings and t_settings.default_country_code else "91"
    try:
        clean_phone = normalize_jid(payload.to_phone, default_country_code=country_code)
    except ValueError as err:
        print(f"[Chats Engine] Rejected manual send target '{payload.to_phone}': {err}")
        raise HTTPException(status_code=400, detail=str(err))

    # 1. Fetch or create conversation channels
    conv = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.customer_phone == clean_phone
    ).first()
    if not conv:
        try:
            conv = Conversation(
                tenant_id=tenant_id,
                session_id=sess.id,
                customer_phone=clean_phone
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
        except Exception:
            db.rollback()
            conv = db.query(Conversation).filter(
                Conversation.tenant_id == tenant_id,
                Conversation.customer_phone == clean_phone
            ).first()

    # Set ownership takeover: pause AI bot for 15 minutes
    from datetime import datetime, timedelta, timezone
    conv.bot_paused_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    # 2. Persist the outbound agent message
    new_msg = Message(
        id=payload.client_uuid if payload.client_uuid else None,
        client_uuid=payload.client_uuid if payload.client_uuid else None,
        conversation_id=conv.id,
        tenant_id=tenant_id,
        session_id=sess.id,
        direction="outbound",
        origin="outbound",
        sender_type="user",
        content=payload.content,
        status="queued",
        ack_state="queued"
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
        "client_uuid": str(new_msg.client_uuid) if new_msg.client_uuid else None,
        "conversation_id": str(new_msg.conversation_id),
        "tenant_id": str(new_msg.tenant_id) if new_msg.tenant_id else None,
        "session_id": str(new_msg.session_id) if new_msg.session_id else None,
        "direction": new_msg.direction,
        "origin": new_msg.origin,
        "sender_type": new_msg.sender_type,
        "content": new_msg.content,
        "status": new_msg.status,
        "ack_state": new_msg.ack_state,
        "whatsapp_message_id": new_msg.whatsapp_message_id,
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
    await websocket_manager.publish_event(str(tenant_id), "message", message_data)
    await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)

    # 4. Request WhatsApp Engine to push message safely in the background
    from app.models.all_models import TenantSetting
    t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
    opts = {
        "replyDelay": t_settings.reply_delay if t_settings else 2,
        "simulateTypingDelay": t_settings.simulate_typing_delay if t_settings else 1000,
        "sendMode": t_settings.send_mode if t_settings else "humanized"
    }

    success = await session_service.send_whatsapp_message(
        session_id=str(sess.id),
        to_phone=clean_phone,
        text=payload.content,
        message_id=str(new_msg.id),
        options=opts
    )

    if not success:
        new_msg.status = "failed"
        new_msg.ack_state = "failed"
        db.commit()
        db.refresh(new_msg)
        message_data["status"] = "failed"
        message_data["ack_state"] = "failed"
        await websocket_manager.publish_event(str(tenant_id), "message_status", message_data)

    return new_msg


from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    conversation_ids: List[UUID]
    delete_type: str = "soft"  # soft, hard, archive

class MergeRequest(BaseModel):
    source_conversation_ids: List[UUID]
    target_jid: str

def purge_conversation_redis_references(session_id: UUID, customer_phone: str):
    """
    Cleans up Redis cache, queues, and references for a deleted conversation.
    Searches the outbound anti-ban queue whatsapp_queue_{session_id} and removes matching items.
    Also registers a short-lived key in Redis to notify the queue worker to abort any mid-flight dispatches.
    """
    import redis
    import json
    from app.config import settings
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        queue_key = f"whatsapp_queue_{session_id}"
        
        # 1. Register ephemeral deletion key to abort mid-flight messages (TTL: 60s)
        lock_key = f"deleted_chat:{session_id}:{customer_phone}"
        r.setex(lock_key, 60, "1")
        print(f"[Queue Purge] Registered short-lived deletion indicator key '{lock_key}' for 60s")

        # 2. Purge matching items from the Baileys outbound queue
        items = r.lrange(queue_key, 0, -1)
        removed_count = 0
        for item in items:
            try:
                payload = json.loads(item.decode('utf-8'))
                to_val = payload.get("to", "")
                # If the outbound JID contains the customer phone/JID, remove it
                if customer_phone in to_val or to_val in customer_phone:
                    r.lrem(queue_key, 0, item)
                    removed_count += 1
            except Exception as parse_err:
                print(f"[Hard Delete] Queue item parse error: {parse_err}")
        if removed_count > 0:
            print(f"[Hard Delete] Purged {removed_count} message(s) from Redis list '{queue_key}' for customer {customer_phone}")
            
    except Exception as e:
        print(f"[Hard Delete] Redis references purge failed: {e}")

@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: UUID, delete_type: str = "soft", tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Deletes a conversation channel (soft, hard, or archive)"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
        
    session_id = conv.session_id
    customer_phone = conv.customer_phone
    
    try:
        if delete_type == "hard":
            db.delete(conv)
            db.commit()
            # Perform Redis queue cleanups and set deletion abort indicator
            purge_conversation_redis_references(session_id, customer_phone)
        elif delete_type == "archive" or delete_type == "soft":
            conv.is_archived = True
            db.commit()
            # Perform Redis queue cleanups and set deletion abort indicator on soft-delete/archive
            purge_conversation_redis_references(session_id, customer_phone)
    except Exception as e:
        db.rollback()
        print(f"[Chats Engine] Delete single failed, transaction rolled back: {e}")
        raise HTTPException(status_code=500, detail="Database transactional rollback occurred during delete.")
    
    # Broadcast delete event to websocket
    from app.core.websocket import websocket_manager
    await websocket_manager.publish_event(str(tenant_id), "conversation_deleted", {
        "id": str(conversation_id),
        "delete_type": delete_type
    })
    
    return {"status": "success", "id": str(conversation_id)}

@router.post("/bulk-delete")
async def bulk_delete_conversations(payload: BulkDeleteRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Bulk deletes/archives conversation channels"""
    convs = db.query(Conversation).filter(
        Conversation.id.in_(payload.conversation_ids),
        Conversation.tenant_id == tenant_id
    ).all()
    
    if not convs:
        return {"status": "success", "count": 0}
        
    # Capture target metadata for purge before they are deleted from DB
    targets = [(c.session_id, c.customer_phone) for c in convs]
    
    try:
        if payload.delete_type == "hard":
            for conv in convs:
                db.delete(conv)
            db.commit()
            # Perform Redis purges after transactional DB commit succeeds
            for sid, phone in targets:
                purge_conversation_redis_references(sid, phone)
        else:
            for conv in convs:
                conv.is_archived = True
            db.commit()
            # Perform Redis purges on soft-delete / archive
            for sid, phone in targets:
                purge_conversation_redis_references(sid, phone)
    except Exception as e:
        db.rollback()
        print(f"[Chats Engine] Bulk delete failed, transaction rolled back: {e}")
        raise HTTPException(status_code=500, detail="Database transactional rollback occurred during bulk delete.")
    
    # Broadcast bulk delete event to websocket
    from app.core.websocket import websocket_manager
    await websocket_manager.publish_event(str(tenant_id), "conversations_bulk_deleted", {
        "ids": [str(c.id) for c in convs],
        "delete_type": payload.delete_type
    })
    
    return {"status": "success", "count": len(convs)}

@router.post("/merge")
async def merge_conversations(payload: MergeRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Merges duplicate conversations into a single target JID channel"""
    from app.core.jid import normalize_jid
    from app.models.all_models import TenantSetting
    t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
    country_code = t_settings.default_country_code if t_settings and t_settings.default_country_code else "91"
    try:
        clean_target_jid = normalize_jid(payload.target_jid, default_country_code=country_code)
    except ValueError as err:
        print(f"[Chats Engine] Rejected merge target '{payload.target_jid}': {err}")
        raise HTTPException(status_code=400, detail=str(err))
    
    # 1. Fetch source conversations
    source_convs = db.query(Conversation).filter(
        Conversation.id.in_(payload.source_conversation_ids),
        Conversation.tenant_id == tenant_id
    ).all()
    if not source_convs:
        raise HTTPException(status_code=400, detail="No valid source conversations found to merge.")
        
    session_id = source_convs[0].session_id
    
    try:
        # 2. Look up or create target conversation
        target_conv = db.query(Conversation).filter(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_phone == clean_target_jid
        ).first()
        
        if not target_conv:
            try:
                target_conv = Conversation(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    customer_phone=clean_target_jid,
                    customer_name=source_convs[0].customer_name or "Merged Customer"
                )
                db.add(target_conv)
                db.commit()
                db.refresh(target_conv)
            except Exception:
                db.rollback()
                target_conv = db.query(Conversation).filter(
                    Conversation.tenant_id == tenant_id,
                    Conversation.customer_phone == clean_target_jid
                ).first()
            
        # 3. Transfer all messages
        for src in source_convs:
            if src.id == target_conv.id:
                continue
            db.query(Message).filter(Message.conversation_id == src.id).update(
                {Message.conversation_id: target_conv.id},
                synchronize_session=False
            )
            db.delete(src)
            
        db.commit()
        db.refresh(target_conv)
    except Exception as e:
        db.rollback()
        print(f"[Chats Engine] Merge duplicate channels failed, transaction rolled back: {e}")
        raise HTTPException(status_code=500, detail="Database transactional rollback occurred during merge.")
    
    # 4. Broadcast merge event to websocket
    from app.core.websocket import websocket_manager
    target_data = {
        "id": str(target_conv.id),
        "tenant_id": str(target_conv.tenant_id),
        "session_id": str(target_conv.session_id),
        "customer_phone": target_conv.customer_phone,
        "customer_name": target_conv.customer_name,
        "is_archived": target_conv.is_archived,
        "last_message_at": target_conv.last_message_at.isoformat() if target_conv.last_message_at else None
    }
    await websocket_manager.publish_event(str(tenant_id), "conversations_merged", {
        "merged_ids": [str(sid) for sid in payload.source_conversation_ids],
        "target_conversation": target_data
    })
    
    return {"status": "success", "target_conversation": target_data}

@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(conversation_id: UUID, payload: ConversationUpdate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Updates conversation memory and settings"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    for field, val in payload.dict(exclude_unset=True).items():
        setattr(conv, field, val)

    db.commit()
    db.refresh(conv)
    return conv

@router.post("/{conversation_id}/handoff", response_model=ConversationResponse)
async def handoff_conversation(conversation_id: UUID, payload: HandoffStatusUpdate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Triggers Human Handoff takeover, disabling the AI bot responses.
    """
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    valid_statuses = ["AI_ACTIVE", "WAITING_AGENT", "HUMAN_ACTIVE", "RESOLVED"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid handoff status: {payload.status}. Must be one of {valid_statuses}")

    conv.handoff_status = payload.status
    conv.bot_override = True if payload.status in ["HUMAN_ACTIVE", "WAITING_AGENT"] else False
    db.commit()
    db.refresh(conv)
    
    # Broadcast status change to websockets
    from app.core.websocket import websocket_manager
    conv_data = {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "session_id": str(conv.session_id),
        "customer_phone": conv.customer_phone,
        "customer_name": conv.customer_name,
        "is_archived": conv.is_archived,
        "handoff_status": conv.handoff_status,
        "bot_override": conv.bot_override,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
    }
    try:
        await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)
    except Exception as e:
        print("[Handoff Websocket] Broadcast failed:", e)

    return conv

@router.post("/{conversation_id}/release", response_model=ConversationResponse)
async def release_conversation(conversation_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Releases conversation from human override back to the AI bot, resetting status to 'RESOLVED' (reactivating AI).
    """
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Mark as resolved to reactivate AI Bot
    conv.handoff_status = "RESOLVED"
    # Also reset bot_paused_until so bot is fully reactivated immediately
    conv.bot_paused_until = None
    conv.bot_override = False
    db.commit()
    db.refresh(conv)

    # Broadcast status change to websockets
    from app.core.websocket import websocket_manager
    conv_data = {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "session_id": str(conv.session_id),
        "customer_phone": conv.customer_phone,
        "customer_name": conv.customer_name,
        "is_archived": conv.is_archived,
        "handoff_status": conv.handoff_status,
        "bot_override": conv.bot_override,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
    }
    try:
        await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)
    except Exception as e:
        print("[Release Websocket] Broadcast failed:", e)

    return conv
