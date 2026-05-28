# Runtime & Telemetry Validation Report

This report documents the live integration tests, API verification checks, and telemetry validations performed on the ReplyOS WhatsApp AI SaaS platform.

---

## 1. Core Service Status Checks

All services are confirmed online and healthy:
```bash
docker compose ps
```
Output:
*   `saas_nginx`: **Up** (Port 8080 gateway reverse-proxying frontend/backend)
*   `saas_frontend`: **Up** (Port 30000 Next.js SSR)
*   `saas_backend`: **Up** (FastAPI backend API)
*   `saas_whatsapp_engine`: **Up** (Baileys WhatsApp instance controller)
*   `saas_worker`: **Up** (Celery background task runner)
*   `saas_postgres`: **Up (healthy)** (PostgreSQL 16 relational DB)
*   `saas_redis`: **Up (healthy)** (Redis queues broker)
*   `saas_ollama`: **Up** (Quantized model inference engine)

---

## 2. API Endpoint Verification

### A. Live Override Outbound Send
Triggered an outbound manual support override message to verify JID routing:
```bash
curl -X POST http://localhost:8080/api/v1/chats/send \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a14b378d-4971-4263-bbe0-b8c63aba71be",
    "to_phone": "185654373789739",
    "content": "Live Override validation from SRE curl",
    "client_uuid": "e1403aed-6f36-4779-bb45-a78ab1aab49e"
  }'
```
Response:
```json
{
  "id": "e1403aed-6f36-4779-bb45-a78ab1aab49e",
  "conversation_id": "847fbc17-2e79-4feb-a959-03a70150ce60",
  "direction": "outbound",
  "sender_type": "user",
  "content": "Live Override validation from SRE curl",
  "status": "queued",
  "created_at": "2026-05-28T13:11:58.201Z"
}
```

### B. Inbound Webhook Event Simulation
Simulated an inbound customer message triggering the background AI chatbot pipeline:
```bash
curl -X POST http://localhost:8080/api/v1/sessions/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "a14b378d-4971-4263-bbe0-b8c63aba71be",
    "event": "message",
    "data": {
      "messageId": "msg_test_inbound_101",
      "from": "185654373789739",
      "pushName": "John Doe",
      "body": "Hi",
      "timestamp": 1780559331
    }
  }'
```
Response:
```json
{
  "status": "queued"
}
```

---

## 3. Telemetry Validation Traces

### A. WhatsApp Engine Logs (Outbound Dispatch Telemetry)
The outbound message telemetry log records execution flows inside `AntiBanQueue.dispatchSafeMessage`:
```text
saas_whatsapp_engine  | [AntiBanQueue - a14b378d-4971-...] BEFORE socket.sendMessage: {
  tenant_id: 'eee18224-de89-41c3-9fb3-e4fdebb532eb',
  session_id: 'a14b378d-4971-4263-bbe0-b8c63aba71be',
  jid: '185654373789739@s.whatsapp.net',
  message_id: 'e1403aed-6f36-4779-bb45-a78ab1aab49e',
  message_body: 'Live Override validation from SRE curl',
  socket_state: 'connected',
  dispatch_source: 'AntiBanQueue'
}
saas_whatsapp_engine  | [AntiBanQueue - a14b378d-4971-...] AFTER socket.sendMessage: {
  tenant_id: 'eee18224-de89-41c3-9fb3-e4fdebb532eb',
  session_id: 'a14b378d-4971-4263-bbe0-b8c63aba71be',
  jid: '185654373789739@s.whatsapp.net',
  message_id: 'e1403aed-6f36-4779-bb45-a78ab1aab49e',
  message_body: 'Live Override validation from SRE curl',
  socket_state: 'connected',
  message_result_id: 'BAE5102930AC',
  dispatch_source: 'AntiBanQueue'
}
```

### B. FastAPI Webhook Logs
```text
saas_backend  | [Webhook - a14b378d-4971-4263-bbe0-b8c63aba71be] Routing to Chatbot: sale
saas_backend  | [Webhook - a14b378d-4971-4263-bbe0-b8c63aba71be] AI reply queued for delivery to 185654373789739
saas_backend  | [ACK Webhook] Message e1403aed-6f36-4779-bb45-a78ab1aab49e status updated to sending
```

---

## 4. Frontend Event Deduplication Validation

*   **Initial optimistic append**: Sends `Message` payload with client-generated UUID string `e1403aed-6f36-4779-bb45-a78ab1aab49e` (status: `sending`).
*   **Websocket push**: Receives `message` event with ID `e1403aed-6f36-4779-bb45-a78ab1aab49e`. Since the ID matches, the Map cache ignores it (no duplicate appended).
*   **API response**: Resolves with message object `e1403aed-6f36-4779-bb45-a78ab1aab49e`. The Map replaces the optimistic reference cleanly. Result: Exactly one bubble rendered.
