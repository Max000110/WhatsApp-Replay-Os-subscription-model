# Message ACK Analysis & State Progression

This document defines how WhatsApp transport status updates (receipt ACKs) are captured, parsed, and stored in the database.

---

## 1. Baileys to System Status Mappings

The Node engine handles numeric receipt codes emitted by the WhatsApp server and translates them to database status strings:

| Baileys Code | WhatsApp Receipt Meaning | System Status Mapping | System `ack_state` |
| :---: | :--- | :--- | :--- |
| `1` | Message is sending from device | `sending` | `sending` |
| `2` | Message successfully reached server | `sent` | `sent` |
| `3` | Message delivered to recipient phone | `delivered` | `delivered` |
| `4` / `5` | Message read by recipient | `read` | `read` |

---

## 2. Webhook Event Transmission

Upon receiving a status event (`messages.update`), the engine triggers a POST webhook request to `/api/v1/sessions/webhook` containing the mapped status:

```json
{
  "sessionId": "a14b378d-4971-4263-bbe0-b8c63aba71be",
  "event": "ack",
  "data": {
    "messageId": "msg_local_uuid",
    "whatsappMessageId": "3EB052D1F55BC40B33A51C",
    "status": "delivered"
  }
}
```

---

## 3. Database Updates & WebSocket Broadcasts

The FastAPI background worker handles the `ack` payload in `process_ack_webhook()`:
1. **Lookup**: Scans the `messages` table for the matching `id` or `whatsapp_message_id`.
2. **Update**: Assigns `msg.status = status` and `msg.ack_state = status`.
3. **Guard**: A status update cannot downgrade. The state can only progress forward:
   `failed (-1) ➔ sending (0) ➔ queued (1) ➔ sent (2) ➔ delivered (3) ➔ read (4)`
4. **Broadcast**: Publishes a `message_status` event via Redis PubSub to synch all active dashboard sessions over WebSockets.

---

## 4. Verification & Lying Checks
The database and WebSockets are verified to reflect the **real physical device state**:
* Sent manual messages or bot replies to un-routable companion JIDs remain permanently as `status = sent` because the WhatsApp server never returns a delivery receipt (`statusVal = 3`).
* Real-device dispatches successfully transition to `status = delivered` and then `read` once the customer's phone confirms delivery and read state, proving no premature state updates occur.
