# Production Debugging & Incident History

This document contains a historical log of critical production bugs, root causes, and fixes implemented on the ReplyOS WhatsApp AI SaaS platform.

---

## 1. Incident RCA-014: AI Bot Replies Fail to Reach Real Devices

### Symptom
Customer messages sent from real WhatsApp devices propagate successfully to the backend, trigger AI responses, and persist in the database, but the outbound bot response never reaches the target phone.

### Root Cause Analysis (RCA)
1. **Mock Phone Mismatch**: In testing environments, simulated inbound messages are triggered using curl webhook scripts with a mock number (`185654373789739`).
2. **Invalid JID Routing**: The AI reply pipeline replies to the mock phone number `185654373789739`. Baileys formats this into `185654373789739@s.whatsapp.net` and attempts transmission.
3. Since `185654373789739` is a fake/invalid phone number, the WhatsApp server accepts the frame (marking its status as `sent` locally) but never delivers it to any real device.
4. When testing using real WhatsApp phones, the message successfully reaches the customer. However, the lack of telemetry logs before and after `sock.sendMessage` made tracking execution difficult.

### Exact Fixes Applied
1. Added database query hooks to pull `tenant_id` on session creation inside `BaileysManager`.
2. Updated the `AntiBanQueue` constructor to accept `tenantId`.
3. Integrated detailed log traces before and after `sock.sendMessage` in `AntiBanQueue.dispatchSafeMessage`, outputting:
   - `tenant_id`
   - `session_id`
   - `jid`
   - `message_id`
   - `message_body`
   - `socket_state`
   - `dispatch_source`

---

## 2. Incident RCA-015: Duplicate Chat Bubble Rendering ("hii" "hii")

### Symptom
When sending an agent manual override message in the live chat panel, the message bubble appears multiple times in the UI.

### Root Cause Analysis (RCA)
1. **Optimistic-WebSocket Race Condition**: When an agent sends a message:
   - The frontend immediately appends a temporary bubble with ID `optimistic-timestamp` (status: `sending`).
   - The API `POST /chats/send` is triggered.
   - The database saves the message and triggers a real-time event via WebSockets with the real UUID `message-id`.
   - The websocket message event fires *before* the API promise resolves. Since the real UUID is not found in the message array, the WebSocket event appends it to the end.
   - The API promise resolves, and tries to replace the optimistic bubble (ID: `optimistic-timestamp`) with the server response (ID: `message-id`).
   - Since both the WebSocket event and API response updates are committed independently, the message is duplicated.

### Exact Fixes Applied
1. **Client-Side UUID Generation**: Integrated browser-compatible UUID generation on the frontend using `crypto.randomUUID()` / custom generator values.
2. The generated UUID is assigned as the `client_uuid` in the payload of `api.chats.sendMessage` and used as the optimistic ID from the beginning.
3. The backend receives `client_uuid` and stores it as the database primary key `id`.
4. Since the optimistic message, API response, and WebSocket event all share the exact same ID, checks like `prev.some(m => m.id === data.id)` automatically catch duplicates.
5. Implemented Map-based deduplication in both WebSocket handlers and background fetch hooks:
   ```typescript
   setMessages((prev) => {
     const map = new Map<string, any>();
     prev.forEach(m => map.set(m.id, m));
     // Deduplicate and override existing values
     return Array.from(map.values());
   });
   ```

---

## 3. Incident RCA-016: Razorpay Sandbox Keys and Mock Payment Bypasses

### Symptom
Payment creation and verification requests fail with Razorpay API Error Code `401 Unauthorized` in production environments when mock parameters are set.

### Root Cause Analysis (RCA)
The API keys defined in environment variables (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`) were sandbox values, causing live order attempts to fail signature checks. The signature verification route allowed bypassing logic if the order ID began with `order_mock_`.

### Exact Fixes Applied
1. Locked order verification to strict production signature validation (using `hmac.compare_digest`).
2. Created a dedicated super-admin manual override route (`POST /admin/tenants/{tenant_id}/activate`) to activate subscriptions when payments fail or require manual intervention, keeping billing logs decoupled.
