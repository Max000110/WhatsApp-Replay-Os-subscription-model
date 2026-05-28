# Real-Time Event & WebSocket Pipeline

This document details the WebSocket server routing, client subscriptions, Nginx reverse proxy mappings, and event JSON schemas.

---

## 1. WebSockets Server Architecture (FastAPI)

WebSocket connections are managed in the backend via a connection coordinator (`WebSocketManager` in `backend/app/core/websocket.py`):

```
       [Client Browser]
              │
              ▼ (WS Connection on /api/v1/ws)
      [saas_nginx Proxy]
              │
              ▼ (Forwards HTTP headers)
[saas_backend WebSocket Route]
              │
    ┌─────────┴─────────┐
    ▼                   ▼
[JWT Verification]  [Subscribes to Redis Channel]
                       "tenant_events:<tenant_id>"
```

### Event Streaming Flow
1.  **WebSocket Handshake**: Client initiates connection to `/api/v1/ws?token=<JWT-Token>`.
2.  **Auth Scoping**: The server decodes the token, extracts `tenant_id`, and authorizes the channel.
3.  **Redis Pub/Sub Subscription**: The backend starts a background task subscribing to the Redis channel `tenant_events:<tenant_id>`.
4.  **Async Broadcast**: When a system event is published:
    - FastAPI calls `publish_tenant_event_sync` which publishes the event to Redis.
    - The backend listener captures the Redis message and forwards it down the active WebSocket client connection.

---

## 2. Nginx Reverse Proxy WS Configuration

To allow WebSocket frames to pass through Nginx, the reverse proxy configuration (`nginx/default.conf`) is configured with the following headers:

```nginx
location /api/v1/ {
    proxy_pass http://backend:8000/api/v1/;
    proxy_http_version 1.1;
    
    # Enable WebSocket upgrades
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 3. WebSocket Event Message Schemas

WebSockets transmit JSON payloads matching this structure:
```json
{
  "type": "message | message_status | session | campaign_status",
  "data": { ... }
}
```

### A. New Message Received (`type = "message"`)
```json
{
  "type": "message",
  "data": {
    "id": "e1403aed-6f36-4779-bb45-a78ab1aab49e",
    "conversation_id": "847fbc17-2e79-4feb-a959-03a70150ce60",
    "direction": "outbound",
    "sender_type": "user",
    "content": "Live Override validation from SRE curl",
    "status": "queued",
    "created_at": "2026-05-28T13:11:58.201Z"
  }
}
```

### B. Message Status ACK Update (`type = "message_status"`)
```json
{
  "type": "message_status",
  "data": {
    "id": "e1403aed-6f36-4779-bb45-a78ab1aab49e",
    "conversation_id": "847fbc17-2e79-4feb-a959-03a70150ce60",
    "status": "sent",
    "whatsapp_message_id": "BAE5102930AC"
  }
}
```

### C. WhatsApp Session Update (`type = "session"`)
```json
{
  "type": "session",
  "data": {
    "id": "a14b378d-4971-4263-bbe0-b8c63aba71be",
    "status": "connected",
    "phone_number": "919137730283",
    "session_name": "Main Account",
    "qr_code": null,
    "reconnect_attempts": 0
  }
}
```
---

## 4. Frontend Reconnection Logic

The Next.js dashboard implements auto-reconnection handling when connections drop:
```javascript
function connectWS() {
  const ws = new WebSocket(`ws://localhost:8080/api/v1/ws?token=${token}`);
  
  ws.onclose = () => {
    console.warn("WebSocket closed. Retrying connection in 3 seconds...");
    setTimeout(connectWS, 3000);
  };
  
  ws.onerror = (err) => {
    console.error("WebSocket encountered error:", err);
    ws.close();
  };
}
```
This ensures high dashboard reliability and synchronization.
