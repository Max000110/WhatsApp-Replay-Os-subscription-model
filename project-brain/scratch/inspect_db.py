import os
import sys

sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.database import SessionLocal
from app.models.all_models import WhatsAppSession, Conversation, Message

def inspect():
    db = SessionLocal()
    try:
        print("--- WHATSAPP SESSIONS ---")
        sessions = db.query(WhatsAppSession).all()
        for s in sessions:
            print(f"ID: {s.id} | Tenant: {s.tenant_id} | Name: {s.session_name} | Phone: {s.phone_number} | Status: {s.status}")
            
        print("\n--- CONVERSATIONS ---")
        convs = db.query(Conversation).all()
        for c in convs:
            print(f"ID: {c.id} | Customer Phone: {c.customer_phone} | Name: {c.customer_name} | Session: {c.session_id} | Paused: {c.bot_paused_until}")
            
        print("\n--- RECENT MESSAGES (last 10) ---")
        msgs = db.query(Message).order_by(Message.created_at.desc()).limit(10).all()
        for m in msgs:
            print(f"ID: {m.id} | Conv: {m.conversation_id} | Dir: {m.direction} | Sender: {m.sender_type} | Content: {m.content[:50]}... | Status: {m.status} | ACK: {m.ack_state}")
            
    except Exception as e:
        print("Error:", e)
    finally:
        db.close()

if __name__ == "__main__":
    inspect()
