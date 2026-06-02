# Live Override Forensics — ReplyOS
**Date**: 2026-05-29 | **Prepared by**: Principal SaaS Reliability Engineer

---

## 1. Executive Summary

A runtime audit of the Live Override (agent manual override) messaging pipeline has been completed. The audit follows the complete lifecycle of a manual agent dispatch:
`Frontend Dashboard` → `API Route (/chats/send)` → `AntiBanQueue` → `Baileys socket.sendMessage()` → `WhatsApp Network` → `ACK Webhook` → `PostgreSQL Database` → `Redis WebSocket Broadcast` → `Frontend Dashboard UI`.

---

## 2. Forensic Investigation & Failure Point

During user testing, a bug was reported: **Dashboard message visible, but customer does NOT receive it on their phone**. 

Our forensics identified the exact failure point:

### 2.1 Failure Location & Metadata
* **Failed File**: `backend/app/routers/sessions.py`
* **Failed Function**: `process_incoming_chat_pipeline`
* **Failed Line**: Line 144
* **Failed Payload (sent to Webhook)**:
  ```json
  {
    "from": "185654373789739",
    "rawRemoteJid": "185654373789739@lid",
    "body": "Hi"
  }
  ```
* **Actual Root Cause**: The backend webhook pipeline resolved the customer JID using the domain-stripped `from` key (`"185654373789739"`) instead of `rawRemoteJid` (`"185654373789739@lid"`). As a result, the database conversation was mapped to `185654373789739@s.whatsapp.net`. When the agent typed a reply, the Live Override sent the message to `185654373789739@s.whatsapp.net` instead of `185654373789739@lid`. The message was transmitted to WhatsApp servers but could not be delivered to the customer, staying in `sent` status indefinitely.

---

## 3. End-to-End Pipeline Audit

| Pipeline Phase | Target Operation | Status | Forensic Evidence / Verification |
|:---|:---|:---|:---|
| **1. Frontend Dashboard** | Agent inputs text and clicks Send. Optimistic bubble rendered in UI. | ✅ PASS | `page.tsx` line 611-628 inserts optimistic state into `messagesMap` with status `sending`. |
| **2. API Route** | `POST /api/v1/chats/send` processes message payload. | ✅ PASS | Returns `200 OK` with JSON matching `SendMessageRequest`. Checks billing status and pauses bot for 15m. |
| **3. Database Write** | Message logged in `messages` table with `status=queued` and `ack_state=queued`. | ✅ PASS | Message UUID generated and row committed to DB. |
| **4. Outbound Queue** | Dispatched to whatsapp-engine `POST /sessions/send`. | ✅ PASS | Handled by `AntiBanQueue` in Redis `whatsapp_queue_{session_id}`. |
| **5. WhatsApp Engine** | Calls `socket.sendMessage(jid, text)`. | ✅ PASS | Socket trace logs `BEFORE socket.sendMessage` and returns network `message_result_id`. |
| **6. ACK updates** | Webhook processes Baileys `messages.update` status changes. | ✅ PASS | Maps numeric statuses: `3 → delivered`, `4 → read` and triggers background DB update. |
| **7. DB Update** | `ack_state` in postgres updated dynamically. | ✅ PASS | Tested and verified: status successfully changes from `queued` → `delivered` → `read` in DB. |
| **8. WebSocket Sync** | Publish event to Redis channel → ws client. | ✅ PASS | UI `messagesMap` merges server response and displays status ticks. |

---

## 4. Remedial Actions

The bug has been fixed:
1. **Webhook Receiver Corrected**: `backend/app/routers/sessions.py` line 144 now checks `data_dict.get("rawRemoteJid")` first:
   ```python
   raw_from = data_dict.get("rawRemoteJid") or data_dict.get("from", "")
   customer_phone = normalize_jid(raw_from)
   ```
2. **Reboot Queue Triggering**: The engine `AntiBanQueue` has been configured to check and trigger queue worker execution on Redis connection initialization, preventing messages from being stuck in queue after restarts.
3. **LID Support Verified**: Normalizer `normalize_jid` successfully resolves `@lid` domains and routing sends to LID endpoints.
