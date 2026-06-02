import os
import sys
import uuid
import asyncio

sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.database import SessionLocal
from app.routers.chats import send_agent_message
from app.schemas.all_schemas import SendMessageRequest
from app.models.all_models import Conversation, Message

async def run_test():
    db = SessionLocal()
    try:
        print("[LiveOverride Test] Triggering manual live override send...")
        
        tenant_id = uuid.UUID("eee18224-de89-41c3-9fb3-e4fdebb532eb")
        session_id = uuid.UUID("a14b378d-4971-4263-bbe0-b8c63aba71be")
        
        payload = SendMessageRequest(
            session_id=session_id,
            to_phone="7021886525", # raw 10-digit number to verify our robust normalization!
            content="Hello from the Live Override testing loop! Checking real device delivery.",
            client_uuid=uuid.uuid4()
        )
        
        # Trigger the router endpoint function directly
        result_msg = await send_agent_message(
            payload=payload,
            tenant_id=tenant_id,
            db=db
        )
        
        print(f"[LiveOverride Test] Endpoint returned successfully. Message ID: {result_msg.id}")
        
        # Verify in database that JID was normalized and conversation/message records exist under canonical form
        db.expire_all()
        conv = db.query(Conversation).filter(
            Conversation.session_id == session_id,
            Conversation.customer_phone == "917021886525@s.whatsapp.net"
        ).first()
        
        assert conv is not None, "Error: Conversation JID was not normalized or conversation record is missing!"
        print(f"[LiveOverride Test] SUCCESS: Conversation resolved under canonical JID: {conv.customer_phone}")
        
        msg = db.query(Message).filter(Message.id == result_msg.id).first()
        assert msg is not None, "Error: Message record is missing from the database!"
        print(f"[LiveOverride Test] SUCCESS: Message record persisted under JID conversation. Content: {msg.content}")
        print(f"[LiveOverride Test] Initial Message status: {msg.status} | ACK: {msg.ack_state}")
        
    except Exception as e:
        print("[LiveOverride Test] ERROR:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_test())
