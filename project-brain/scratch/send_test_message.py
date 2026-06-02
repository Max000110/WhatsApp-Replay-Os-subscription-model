import os
import sys
import asyncio

sys.path.append("/home/ubuntu/whatsapp-ai-saas/backend")

from app.services.session_service import session_service

async def send():
    session_id = "a14b378d-4971-4263-bbe0-b8c63aba71be"
    to_phone = "917021886525@s.whatsapp.net"
    text = "Hello from Antigravity! Direct test message."
    
    print(f"Sending message to {to_phone} via session {session_id}...")
    success = await session_service.send_whatsapp_message(
        session_id=session_id,
        to_phone=to_phone,
        text=text
    )
    print("Success:", success)

if __name__ == "__main__":
    asyncio.run(send())
