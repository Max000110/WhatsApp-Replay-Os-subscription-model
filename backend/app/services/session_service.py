import httpx
from sqlalchemy import text
from app.config import settings

class SessionService:
    """
    Session Service handling outbound API requests to the Node.js Baileys WhatsApp Engine.
    Communicates across Docker internal networks using async httpx.
    """

    def __init__(self):
        self.engine_url = settings.WHATSAPP_ENGINE_URL

    async def trigger_live_agent_override(self, conversation_id: str, agent_id: str, db, tenant_id: str):
        """
        Flush internal bot context instantly when human agent connects.
        Overrides the state transition flags from red to CONNECTED_GREEN.
        """
        db.execute(
            text("UPDATE conversations SET handoff_status = 'HUMAN_ACTIVE', bot_override = TRUE WHERE id = :id"),
            {"id": conversation_id}
        )
        db.commit()
        
        # Broadcast green-state active flag via WebSockets to Next.js dashboard
        from app.core.websocket import websocket_manager
        await websocket_manager.publish_event(
            str(tenant_id),
            "conversation",
            {
                "id": str(conversation_id),
                "status": "CONNECTED_GREEN",
                "agent": str(agent_id),
                "handoff_status": "HUMAN_ACTIVE",
                "bot_override": True
            }
        )

    async def init_whatsapp_connection(self, session_id: str) -> bool:
        """
        Signals the WhatsApp Engine to load/restore or generate a QR code for a session
        """
        url = f"{self.engine_url}/sessions/init"
        payload = {"sessionId": str(session_id)}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=payload)
                return res.status_code in [200, 202]
            except Exception as err:
                print(f"[SessionService] Failed to trigger session init {session_id}:", err)
                return False

    async def send_whatsapp_message(
        self,
        session_id: str,
        to_phone: str,
        text: str,
        message_id: str = None,
        options: dict = None
    ) -> bool:
        """
        Enqueues an outbound WhatsApp message inside the Node service anti-ban system
        """
        url = f"{self.engine_url}/sessions/send"
        payload = {
            "sessionId": str(session_id),
            "to": to_phone,
            "text": text,
            "messageId": str(message_id) if message_id else None,
            "options": options or {}
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=payload)
                return res.status_code == 200
            except Exception as err:
                print(f"[SessionService] Failed to dispatch outbound to {to_phone}:", err)
                return False

session_service = SessionService()
