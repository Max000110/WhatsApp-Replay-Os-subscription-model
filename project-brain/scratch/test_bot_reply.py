import os
import sys
import uuid
import asyncio

sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.database import SessionLocal
from app.models.all_models import Conversation, Message, Chatbot
from app.routers.sessions import process_incoming_chat_pipeline

async def run_test():
    db = SessionLocal()
    try:
        print("[BotReply Test] Commencing AI Bot auto-reply loop test...")
        
        session_id = "a14b378d-4971-4263-bbe0-b8c63aba71be"
        
        # 1. Ensure conversation is unpaused
        conv = db.query(Conversation).filter(
            Conversation.customer_phone == "917021886525@s.whatsapp.net"
        ).first()
        if conv:
            conv.bot_paused_until = None
            db.commit()
            print("[BotReply Test] Bot unpaused successfully for conversation.")
            
        # 2. Make sure chatbot is active and has system prompt
        bot = db.query(Chatbot).filter(
            Chatbot.session_id == uuid.UUID(session_id),
            Chatbot.is_active == True
        ).first()
        if not bot:
            print("[BotReply Test] Creating a fallback chatbot 'sales' for testing...")
            bot = Chatbot(
                tenant_id=uuid.UUID("eee18224-de89-41c3-9fb3-e4fdebb532eb"),
                session_id=uuid.UUID(session_id),
                name="sales",
                system_prompt="You are a professional sales assistant for ReplyOS SaaS. Keep responses short and helpful.",
                model_name="qwen2.5:1.5b-instruct",
                is_active=True
            )
            db.add(bot)
            db.commit()
            
        print(f"[BotReply Test] Active Chatbot: '{bot.name}' | Model: {bot.model_name}")
        
        # 3. Simulate inbound WhatsApp message
        event_data = {
            "from": "917021886525@s.whatsapp.net",
            "body": "What services do you offer?",
            "pushName": "Afzal",
            "messageId": f"MOCK_{uuid.uuid4().hex[:16]}",
            "timestamp": 1716943890
        }
        
        print("[BotReply Test] Simulating webhook trigger process...")
        # Execute the pipeline background task synchronously
        await process_incoming_chat_pipeline(
            session_id=session_id,
            event="message",
            data_dict=event_data
        )
        print("[BotReply Test] Webhook simulation completed.")
        
    except Exception as e:
        print("[BotReply Test] ERROR:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_test())
