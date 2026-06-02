# Raw Baileys Payloads & JID Corruption Trace

This document captures the raw structures of incoming WhatsApp message payloads received via Baileys sockets and traces the exact logical execution path from socket events to front-end dashboard rendering.

---

## 1. Raw Baileys Payload Schema

When a message is received on the active WhatsApp Web TCP socket, the Baileys engine (`@whiskeysockets/baileys`) fires a `messages.upsert` event containing the following message frame:

```json
{
  "key": {
    "remoteJid": "18565437378:9739@s.whatsapp.net",
    "fromMe": false,
    "id": "3EB053BBEAEFE35DCE7494",
    "participant": null
  },
  "message": {
    "conversation": "Hello from the companion device!"
  },
  "messageTimestamp": 1780004921,
  "pushName": "John Doe"
}
```

### Telemetry Target Keys

* **`message.key.id`**: Unique ID of the message frame (`3EB053BBEAEFE35DCE7494`).
* **`message.key.remoteJid`**: JID of the sender session (`18565437378:9739@s.whatsapp.net` or `185654373789739@lid`).
* **`message.key.participant`**: Sender JID in group contexts (empty `null` in DMs).
* **`message.pushName`**: The profile display name of the customer (`John Doe`).
* **`message.message`**: The inner message body type (e.g., `conversation` or `extendedTextMessage`).
* **`message.messageTimestamp`**: UNIX timestamp of the transmission.

---

## 2. In-Depth End-to-End Delivery Trace

Below is the complete architectural trace of an incoming message frame passing through all platform subsystems:

```mermaid
graph TD
    A[Raw Baileys Message Upsert] -->|remoteJid = 18565437378:9739@s.whatsapp.net| B[JID Extractor: split ':' and '@']
    B -->|from = 18565437378| C[Express: POST /sessions/webhook]
    C -->|from = 18565437378| D[FastAPI: sessions.py Webhook Ingest]
    D -->|normalize_jid| E[app.core.jid.normalize_jid]
    E -->|18565437378@s.whatsapp.net| F[Conversation Resolver: find/create]
    F -->|conversations.customer_phone| G[PostgreSQL Database Commit]
    G -->|PubSub Event| H[Redis Message Broker]
    H -->|WebSocket Broadcast| I[FastAPI: websockets.py]
    I -->|JSON Frame| J[Next.js Frontend: page.tsx WS Listener]
    J -->|conversationsMap.set| K[Deduplicated Map Store Render]
```

### Layer Telemetry Details

1. **Raw Baileys Event**:
   * Socket event `messages.upsert` receives the raw frame.
   * `msg.key.remoteJid` holds the companion JID: `18565437378:9739@s.whatsapp.net` or LID JID: `185654373789739@lid`.

2. **JID Extractor (`baileys-manager.ts`)**:
   * Extracts clean phone number:
     ```typescript
     const from = remoteJid?.split("@")[0].split(":")[0] || "";
     ```
   * Splits at `@` ➔ `18565437378:9739`.
   * Splits at `:` ➔ `18565437378` (Primary contact identifier).

3. **FastAPI normalize_jid() (`jid.py`)**:
   * Normalizes the JID into standard form:
     ```python
     user = user_clean.split(":", 1)[0]
     # Prepend 91 for Indian 10-digit numbers
     if len(user) == 10 and user[0] in '6789':
         user = '91' + user
     return f"{user}@s.whatsapp.net"
     ```
   * Formats into a clean target identity: `18565437378@s.whatsapp.net`.

4. **Conversation Resolver (`sessions.py`)**:
   * Queries `Conversation` table by `customer_phone == clean_jid`.
   * Creates or resolves the single canonical chat thread to ensure "one customer = one conversation".

5. **Database Commit**:
   * Stores the message row in the `messages` table with status `"read"`.

6. **WebSocket Dispatch**:
   * Broadcasts `message` and `conversation` updates to the active tenant workspace channel:
     ```python
     await websocket_manager.publish_event(str(tenant_id), "message", message_data)
     ```

7. **Frontend Reduction (`page.tsx`)**:
   * Integrates the message directly into the Map stores:
     ```typescript
     setConversationsMap((prev) => new Map(prev).set(conv.customer_phone, conv));
     ```
   * Enforces O(1) deduplication, avoiding duplicate threads.

---

## 3. Forensic Analysis: Exact Layer of Historical JID Corruption

### Symptom
Prior test sessions resulted in the database registering a malformed customer identity:
`185654373789739@s.whatsapp.net`

### The Exact Corruption Layers
The JID corruption was caused by a combination of unaligned logic between the Node.js Express server and the Python FastAPI backend:

1. **Express Engine Extraction Failure**:
   The older `baileys-manager.ts` code parsed the incoming remote JID by splitting only at the `@` symbol:
   ```typescript
   // OLD MANGLED LOGIC
   const from = remoteJid?.split("@")[0] || "";
   ```
   For the companion device `18565437378:9739@s.whatsapp.net`, it extracted `"18565437378:9739"` and forwarded it to the webhook backend.

2. **FastAPI Indiscriminate Cleaning**:
   On receiving `"18565437378:9739"`, the previous python JID normalizer cleaned non-digits globally using a regex:
   ```python
   # OLD CORRUPTING LOGIC
   clean_digits = re.sub(r"\D", "", phone_input)
   ```
   Because `\D` matches anything that is not a digit, the colon `:` was stripped, turning `"18565437378:9739"` into `"185654373789739"`. This resulted in the 15-digit malformed phone number being committed to PostgreSQL as `185654373789739@s.whatsapp.net`.

### Corrective Real-World Logic
* **Express JID Split**: Sockets now split by `:` first, ensuring that `18565437378:9739` is immediately reduced to `18565437378` at the engine boundary.
* **FastAPI Colon Isolation**: Backend normalizer uses `.split(":", 1)[0]` instead of blanket non-digit replacements, preserving clean international and domestic identities under a strict formatting checklist.
