import os
import sys
import uuid
from datetime import datetime, timezone

# Add backend directory to path
sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.database import SessionLocal
from app.models.all_models import Conversation, Message

def run_test():
    db = SessionLocal()
    try:
        print("[Test] Commencing Database Deletion & Cascade Constraint Verification...")
        
        tenant_id = uuid.UUID("eee18224-de89-41c3-9fb3-e4fdebb532eb")
        session_id = uuid.UUID("a14b378d-4971-4263-bbe0-b8c63aba71be")
        
        # 1. Seed a test conversation
        test_conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            session_id=session_id,
            customer_phone="917021886525@s.whatsapp.net",
            customer_name="Afzal",
            is_archived=False
        )
        db.add(test_conv)
        db.commit()
        db.refresh(test_conv)
        print(f"[Test] Test conversation successfully seeded: ID={test_conv.id}")
        
        # 2. Seed dependent messages
        msg_count = 5
        messages = []
        for i in range(msg_count):
            msg = Message(
                id=uuid.uuid4(),
                conversation_id=test_conv.id,
                tenant_id=tenant_id,
                session_id=session_id,
                direction="inbound" if i % 2 == 0 else "outbound",
                origin="inbound" if i % 2 == 0 else "outbound",
                sender_type="customer" if i % 2 == 0 else "bot",
                content=f"Test message transcript index #{i}",
                status="delivered",
                ack_state="delivered"
            )
            db.add(msg)
            messages.append(msg)
            
        db.commit()
        print(f"[Test] Successfully seeded {msg_count} dependent messages.")
        
        # Verify seeding in database
        seeding_verify_conv = db.query(Conversation).filter(Conversation.id == test_conv.id).first()
        seeding_verify_msgs = db.query(Message).filter(Message.conversation_id == test_conv.id).all()
        assert seeding_verify_conv is not None, "Seeded conversation was not saved!"
        assert len(seeding_verify_msgs) == msg_count, f"Expected {msg_count} messages, found {len(seeding_verify_msgs)}"
        print("[Test] Seeding database checks passed successfully.")
        
        # 3. Perform a Hard Delete on the conversation to trigger CASCADE purging
        print(f"[Test] Executing atomic hard delete on conversation ID {test_conv.id}...")
        db.delete(test_conv)
        db.commit()
        print("[Test] Hard delete transaction successfully committed.")
        
        # 4. Verify cascade deletions (No orphan messages or residual rows)
        verify_conv = db.query(Conversation).filter(Conversation.id == test_conv.id).first()
        verify_msgs = db.query(Message).filter(Message.conversation_id == test_conv.id).all()
        
        print(f"[Test] Post-delete check: Conversation exists? {verify_conv is not None}")
        print(f"[Test] Post-delete check: Orphan message rows count? {len(verify_msgs)}")
        
        assert verify_conv is None, "Conversation was not hard deleted!"
        assert len(verify_msgs) == 0, f"Cascade deletion failed! Found {len(verify_msgs)} orphan messages."
        
        print("\n✅ SUCCESS: Cascade rules and atomic transactional hard deletion checks passed flawlessly!")
        
    except Exception as err:
        db.rollback()
        print(f"\n❌ FAILURE: Database deletion test failed with exception: {err}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_test()
