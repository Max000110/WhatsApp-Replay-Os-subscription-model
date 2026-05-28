# Production-Grade Debugging & Infrastructure Repair Report

**Target Infrastructure**: Multi-Container WhatsApp AI SaaS Stack  
**Public VM IP**: `144.24.126.153`  
**Host Ports**: `8080` (Nginx Gateway), `30000` (Direct Frontend SSR)

---

## 1. Historical Root Cause Analysis (Phases 1–3)

### Bug A: CORS Wildcard with Credentials Conflict (RCA-001)
- **File**: `backend/app/main.py`
- **RCA**: `allow_origins=["*"]` + `allow_credentials=True` violates W3C CORS spec. Fixed with explicit origin list.

### Bug B: Misleading Fetch Error Masking (RCA-002)
- **File**: `frontend/src/lib/api.ts`
- **RCA**: `response.json().catch(() => ({}))` silently swallowed non-JSON errors. Fixed with two-layer error decoder (JSON → text → status code fallback).

### Bug C: Nginx Path Stripping & Buffer Limits (RCA-003)
- **File**: `nginx/default.conf`
- **RCA**: Trailing path on `proxy_pass` caused route mismatches; no buffer tuning caused 502s. Fixed with bare host proxy + 128k/256k buffers.

### Bug D: passlib-bcrypt Version Clash (RCA-004)
- **File**: `backend/requirements.txt`
- **RCA**: `bcrypt >= 4.x` raises `ValueError` on passwords > 72 bytes during passlib self-test. Fixed by pinning `bcrypt==3.2.2`.

### Bug E: Baileys Protocol Version Mismatch (RCA-005)
- **File**: `whatsapp-engine/src/baileys-manager.ts`
- **RCA**: Hardcoded protocol version `2.3000.x` caused `405 Outdated` disconnects. Fixed with dynamic `fetchLatestBaileysVersion()` on socket creation.

### Bug F: Socket Leak / Reconnect Storm (RCA-006)
- **File**: `whatsapp-engine/src/baileys-manager.ts` → `cleanupSession()`
- **RCA**: Old event listeners not removed before socket replacement causing parallel connection loops. Fixed by `removeAllListeners()` + `socket.end(undefined)`.

### Bug G: Redis Not Mounted in WhatsApp Engine (RCA-007)
- **File**: `docker-compose.yml`
- **RCA**: `REDIS_URL` not in `whatsapp-engine` env block; engine fell back to immediate dispatch bypassing anti-ban queue. Fixed by adding `REDIS_URL` and `depends_on: redis` to the service.

### Bug H: JID Double-Suffix Normalization (RCA-008)
- **File**: `whatsapp-engine/src/anti-ban.ts`
- **RCA**: Phone numbers stored as `185654373789739` were appended `@s.whatsapp.net` to produce valid JIDs. But if a value already contained `@s.whatsapp.net`, the old logic double-appended it to `number@s.whatsapp.net@s.whatsapp.net`. Fixed with correct guard: `if (!cleanJid.includes('@'))`.

---

## 2. Phase 4 – Frontend Live Override Panel Integration Bugs

> All backend systems verified healthy via direct curl. Root cause narrowed to frontend.

### Bug I: Input Cleared Before API Response (RCA-009) ← CRITICAL UX BUG

**File**: `frontend/src/app/dashboard/page.tsx` → `handleSendAgentMessage()` (line 190)

**Broken code**:
```javascript
const handleSendAgentMessage = async (e) => {
  e.preventDefault();
  if (!agentMsgText.trim() || !activeConv) return;
  try {
    const txt = agentMsgText;
    setAgentMsgText('');        // ← CLEARED HERE, BEFORE AWAIT
    const res = await api.chats.sendMessage({...});
    setMessages([...messages, res]);
  } catch (err) {
    alert(err.message);         // ← ONLY FEEDBACK, EASILY MISSED
  }
};
```

**Effect**: Input clears immediately creating false sense of success. If API fails, the typed message is gone and only a dismissable `alert()` signals failure. User interprets cleared input as "sent" even when WhatsApp never received the message.

**Fix**: Optimistic message bubble is added to thread immediately with `status: 'sending'`. Input is cleared. On API success, optimistic bubble is replaced with real server response. On API failure, optimistic bubble is removed, input text is restored, and an **inline error banner** is shown inside the chat panel (no more `alert()`).

---

### Bug J: Stale `messages` Closure in State Update (RCA-010)

**File**: `frontend/src/app/dashboard/page.tsx` → `handleSendAgentMessage()` (line 203)

**Broken code**:
```javascript
setMessages([...messages, res]);  // ← 'messages' is a stale captured reference
```

**Effect**: The 3-second polling `setInterval` continually re-renders the component. The send handler captures the `messages` array from the render when it was defined. If polling runs between when the handler fires and when `await` resolves, the state update uses an old `messages` slice, potentially losing messages.

**Fix**: Use functional update form: `setMessages(prev => [...prev, res])` — always operates on the latest state regardless of closures.

---

### Bug K: `activeConv` Never Refreshed by Polling (RCA-011)

**File**: `frontend/src/app/dashboard/page.tsx` → `fetchDashboardCoreData()` (line 63)

**Broken code**:
```javascript
const convList = await api.chats.list();
setConversations(convList);
// ← activeConv is NEVER refreshed from here
```

**Effect**: `activeConv` is set once when the user clicks a conversation. The 5-second background poller refreshes `activeSession` but NOT `activeConv`. If server-side data changes (e.g., `session_id` or `last_message_at` updates), the send payload uses the stale snapshot captured at click time.

Additionally, `fetchDashboardCoreData` is captured by `setInterval` at mount time as a stale closure that never sees updated `activeSession` or `activeKb` values.

**Fix**:
1. Converted `fetchDashboardCoreData` to `useCallback` with stable reference.
2. Added `useRef` for `activeConvRef` and `activeKbRef` — refs are kept in sync via dedicated `useEffect`s.
3. After refreshing the conversations list, find and re-set `activeConv` from the fresh data using the ref.

---

### Bug L: No Send Guard — Duplicate In-Flight Requests (RCA-012)

**File**: `frontend/src/app/dashboard/page.tsx` → send button (line 736)

**Broken code**:
```jsx
<button type="submit" className="bg-primary ...">
  <Send className="h-4 w-4" />
</button>
```

**Effect**: No `disabled` state during async send. Rapid double-clicks fire multiple `POST /chats/send` requests simultaneously, sending duplicate messages to WhatsApp.

**Fix**: Added `isSending` boolean state. Button is disabled + shows `<Loader2 animate-spin>` while request is in-flight. Input field is also disabled and shows "Sending to WhatsApp..." placeholder.

---

### Bug M: Polling Overwrites Optimistic Messages (RCA-013)

**File**: `frontend/src/app/dashboard/page.tsx` → `fetchHistory` inside `useEffect` (line 97)

**Broken code**:
```javascript
const msgList = await api.chats.getMessages(activeConv.id);
setMessages(msgList);  // ← unconditionally overwrites, including in-flight optimistic bubbles
```

**Effect**: The 3-second polling unconditionally replaces `messages` state with server data. If a send is in flight (optimistic bubble has `id: 'optimistic-...'`), the poll fires mid-send, removes the optimistic bubble, and replaces it with server data that doesn't yet include the message being sent. This causes the thread to flash/flicker.

**Fix**: Polling uses functional update with pending-check guard:
```javascript
setMessages(prev => {
  const hasPending = prev.some(m => String(m.id).startsWith('optimistic-'));
  if (hasPending) return prev;  // Don't overwrite in-flight sends
  return msgList;
});
```

---

## 3. Complete Applied Patches

### A. `frontend/src/app/dashboard/page.tsx`

```diff
- import React, { useState, useEffect } from 'react';
+ import React, { useState, useEffect, useRef, useCallback } from 'react';

- Send, User, Clock, ..., AlertCircle
+ Send, User, Clock, ..., AlertCircle, Loader2

  // New state variables added:
+ const [isSending, setIsSending] = useState(false);
+ const [sendError, setSendError] = useState('');
+ const activeConvRef = useRef<any>(null);
+ const activeKbRef = useRef<any>(null);
+ const messagesEndRef = useRef<HTMLDivElement>(null);
+ useEffect(() => { activeConvRef.current = activeConv; }, [activeConv]);
+ useEffect(() => { activeKbRef.current = activeKb; }, [activeKb]);
+ useEffect(() => {
+   messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
+ }, [messages]);

- const fetchDashboardCoreData = async () => { ... };
+ const fetchDashboardCoreData = useCallback(async () => {
+   // ... refreshes activeConv from fresh server data using activeConvRef ...
+ }, []);

  // In fetchHistory useEffect:
- setMessages(msgList);
+ setMessages(prev => {
+   if (prev.some(m => String(m.id).startsWith('optimistic-'))) return prev;
+   return msgList;
+ });

  // handleSendAgentMessage rewritten:
- const handleSendAgentMessage = async (e) => {
-   const txt = agentMsgText;
-   setAgentMsgText('');
-   const res = await api.chats.sendMessage({...});
-   setMessages([...messages, res]);
- };
+ const handleSendAgentMessage = async (e) => {
+   if (!txt || !activeConv || isSending) return;
+   setIsSending(true);
+   // Add optimistic bubble immediately
+   setMessages(prev => [...prev, { id: `optimistic-${Date.now()}`, status: 'sending', ... }]);
+   setAgentMsgText('');
+   try {
+     const res = await api.chats.sendMessage({ session_id: conv.session_id, ... });
+     setMessages(prev => prev.map(m => m.id === optimisticId ? res : m)); // replace optimistic
+   } catch (err) {
+     setMessages(prev => prev.filter(m => m.id !== optimisticId)); // remove optimistic
+     setAgentMsgText(txt); // restore input
+     setSendError(err.message); // show inline error banner
+   } finally {
+     setIsSending(false);
+   }
+ };
```

---

## 4. Final Runtime Validation Evidence

### Backend /chats/send curl test (HTTP 200):
```
HTTP/1.1 200 OK
{"id":"e66f2aa7-cb6d-4c35-be43-f9005f6743e2","direction":"outbound","sender_type":"user","status":"sent","content":"Live override hello from SRE curl!"}
```

### WhatsApp Engine dispatch confirmation:
```
[AntiBanQueue - a14b378d-...] Safe dispatch succeeded to 185654373789739@s.whatsapp.net
[AntiBanQueue - a14b378d-...] Safe dispatch succeeded to 185654373789739@s.whatsapp.net
[AntiBanQueue - a14b378d-...] Safe dispatch succeeded to 185654373789739@s.whatsapp.net
```

### PostgreSQL messages table (outbound user messages persisted):
```
 sender_type | status |   content
-------------+--------+------------------
 user        | sent   | hii
 user        | sent   | hi
 user        | sent   | Live override hello from SRE curl!
```

### Database conversation state:
```
customer_phone: 185654373789739   ← clean digits, no JID suffix
session_id: a14b378d-4971-4263-bbe0-b8c63aba71be  ← connected session
```

---

## 5. Rebuild Commands Applied

```bash
docker compose build frontend
docker compose up -d frontend
docker compose restart nginx
```
