import os
import sys
import uuid
import asyncio

sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.database import SessionLocal
from app.routers.chats import delete_conversation
from app.models.all_models import Conversation, Message

async def run_test():
    db = SessionLocal()
    try:
        print("[HardDelete Test] Commencing conversation hard delete...")
        
        tenant_id = uuid.UUID("eee18224-de89-41c3-9fb3-e4fdebb532eb")
        
        # 1. Fetch our active test conversation
        conv = db.query(Conversation).filter(
            Conversation.customer_phone == "917021886525@s.whatsapp.net"
        ).first()
        
        assert conv is not None, "Error: Test conversation fb6fa725-12a6-4be3-8376-008f53f4865a not found in database!"
        conversation_id = conv.id
        print(f"[HardDelete Test] Found active conversation to delete: ID={conversation_id}")
        
        # Verify message count before delete
        before_msgs_count = db.query(Message).filter(Message.conversation_id == conversation_id).count()
        print(f"[HardDelete Test] Messages count before delete: {before_msgs_count}")
        assert before_msgs_count > 0, "Error: Seeded messages are missing!"
        
        # 2. Trigger the delete_conversation route synchronously
        result = await delete_conversation(
            conversation_id=conversation_id,
            delete_type="hard",
            tenant_id=tenant_id,
            db=db
        )
        print("[HardDelete Test] Delete endpoint returned success:", result)
        
        # 3. Assert cascade purging
        db.expire_all()
        after_conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        after_msgs_count = db.query(Message).filter(Message.conversation_id == conversation_id).count()
        
        print(f"[HardDelete Test] Post-delete check: Conversation exists? {after_conv is not None}")
        print(f"[HardDelete Test] Post-delete check: Orphan messages count? {after_msgs_count}")
        
        assert after_conv is None, "Error: Conversation record was not hard deleted!"
        assert after_msgs_count == 0, f"Error: Cascade delete failed! Found {after_msgs_count} orphan messages."
        print("\n✅ SUCCESS: Cascade rules and atomic transactional hard deletion completed flawlessly!")
        
    except Exception as e:
        print("[HardDelete Test] ERROR:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_test())
