# WhatsApp Message Delivery Pipeline

This document defines the end-to-end routing architecture for all outbound WhatsApp messages across campaign dispatches, live chat overrides, and AI bot replies.

---

## 1. Unified Outbound Architecture

All three message dispatch channels converge onto a single unified backend service execution path:

```
[Campaign Dispatch (Celery Worker)] ─┐
                                      ├─> [session_service.send_whatsapp_message()]
[Live Chat Override (chats.py)] ──────┤                       │
                                      │                       ▼ (Docker Network HTTP)
[AI Bot Auto-Reply (sessions.py)] ────┘             [whatsapp-engine:3000/sessions/send]
                                                              │
                                                              ▼
                                                    [AntiBanQueue (anti-ban.ts)]
                                                              │
                                                              ▼ (Safe Delays / Jitter)
                                                    [socket.sendMessage() (Baileys)]
```

### Routing Convergence Point
* **Backend Call**: [session_service.send_whatsapp_message(session_id, to_phone, text, message_id)](file:///home/ubuntu/whatsapp-ai-saas/backend/app/services/session_service.py#L28-L46)
* **API Transfer**: Internal HTTP request from FastAPI `saas_backend` container to Express `saas_whatsapp_engine` container on port `3000` via route `/sessions/send`.

---

## 2. JID Normalization & Companion Devices

To avoid un-routable message requests, phone numbers and JIDs are sanitized to eliminate companion device suffixes (colons `:` and device/agent IDs).

### Target Formatting Rules
1. **Remove Special Symbols**: Strip spaces and plus signs (`+`) from the phone number.
2. **Strip Device Suffixes**: Split the number/user part by `:` and take the first index to remove device-specific routing. E.g., `18565437378:9739` normalizes to `18565437378`.
3. **Assemble Primary JID**: Target JID MUST be formatted as `[clean_phone]@s.whatsapp.net`.

### Code Implementation Points
* **whatsapp-engine (Inbound & ACK Webhooks)**: [baileys-manager.ts](file:///home/ubuntu/whatsapp-ai-saas/whatsapp-engine/src/baileys-manager.ts#L171) normalizes `from` numbers:
  ```typescript
  const from = remoteJid?.split("@")[0].split(":")[0] || "";
  ```
* **whatsapp-engine (Outbound Normalization)**: [anti-ban.ts](file:///home/ubuntu/whatsapp-ai-saas/whatsapp-engine/src/anti-ban.ts#L34-L41) sanitizes target JID:
  ```typescript
  let cleanJid = to.trim().replace(/\s+/g, "").replace("+", "");
  if (cleanJid.includes("@")) {
    const [user, domain] = cleanJid.split("@");
    cleanJid = `${user.split(":")[0]}@${domain}`;
  } else {
    cleanJid = `${cleanJid.split(":")[0]}@s.whatsapp.net`;
  }
  ```
* **FastAPI Backend (Live Override Send)**: [chats.py](file:///home/ubuntu/whatsapp-ai-saas/backend/app/routers/chats.py#L60) strips colons from input:
  ```python
  clean_phone = payload.to_phone.replace("+", "").replace(" ", "").split(":")[0]
  ```

---

## 3. Anti-Ban Queue Mechanism

All messages are queued in a sliding Redis list `whatsapp_queue_[session_id]` to model human texting behavior and protect lines from being banned.

### Safety Operations & Jitter
1. **Composing Presence**: Triggers WhatsApp typing indicator (`composing` state) when dequeueing a message.
2. **Simulated Typing Latency**: Dynamic wait delay based on message length (~20ms per character, capped at `3500ms`).
3. **Safety Jitter**: Additional random delay of `4000ms` - `8000ms` between sequential message sends.
4. **Typing Off**: Triggers typing indicator `paused` state before sending.
5. **WhatsApp API Call**: Executes Baileys `socket.sendMessage(jid, { text })` asynchronously.

---

## 4. Webhook Status Feedback & ACK States

After socket transmission, status changes are tracked via the webhook pipeline:

* **Engine status update webhook**: Express reports events (`sending`, `sent`, `failed`, `delivered`, `read`) back to FastAPI `/api/v1/sessions/webhook`.
* **State updates**: Backend updates message row state (`status` and `ack_state`) and publishes events via Redis PubSub to frontend WebSocket clients.
* **ACK Progression Constraint**: Statuses can only advance and never degrade:
  `failed` (-1) ➔ `sending` (0) ➔ `queued` (1) ➔ `sent` (2) ➔ `delivered` (3) ➔ `read` (4)
