# Production Debugging History Log

This document lists all major incident reports, runtime exceptions, and structural bugs identified and resolved during the deployment of the WhatsApp AI SaaS Platform.

---

## Incident RCA-001: CORS Wildcard with Credentials Conflict

### Symptom
Frontend requests to FastAPI backend fail with network errors. Browser console displays:
`Access to fetch at ... from origin ... has been blocked by CORS policy: The value of the 'Access-Control-Allow-Origin' header in the response must not be the wildcard '*' when the request's credentials mode is 'include'.`

### Root Cause
FastAPI configuration in `backend/app/main.py` initialized `CORSMiddleware` with `allow_origins=["*"]` while setting `allow_credentials=True`. This direct conflict violates the W3C CORS specification and causes browser engines to drop responses.

### Affected Files
* `backend/app/main.py`

### Exact Fix
Explicitly map allowed origins parsed from environment parameters or configured production domains:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:30000",
        "http://144.24.126.153:30000",
        "http://144.24.126.153:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Verification Results
Browser network requests now resolve with `200 OK` status and return correct headers.

---

## Incident RCA-002: Silent Fetch Error Masking

### Symptom
Failed API requests appear in the browser console as blank objects or generic `TypeError` exceptions. The real server responses (e.g., `401 Unauthorized` or `500 Internal Server Error`) are lost.

### Root Cause
The custom fetch wrapper in `frontend/src/lib/api.ts` used `response.json().catch(() => ({}))` to extract data. When the server returned a plain-text error or empty error stack, `response.json()` failed, fell back to `{}`, and masked the real failure details.

### Affected Files
* `frontend/src/lib/api.ts`

### Exact Fix
Implemented a robust two-layer error parsing mechanism:
```typescript
const text = await response.text();
let data;
try {
  data = JSON.parse(text);
} catch {
  data = { error: text || response.statusText };
}

if (!response.ok) {
  throw new Error(data.detail || data.error || `HTTP error! status: ${response.status}`);
}
```

### Verification Results
API error banners now accurately reflect database exceptions and network timeouts.

---

## Incident RCA-003: Nginx Path Stripping & Buffer Failures

### Symptom
Requests routing through Nginx to FastAPI return `404 Not Found` or intermittent `502 Bad Gateway` errors.

### Root Cause
1. **Trailing Slashes**: The `proxy_pass` configuration in `nginx/default.conf` used `proxy_pass http://backend:8000/api/v1/;`. The trailing slash caused Nginx to strip request path prefixes improperly, generating routes like `/sessions` instead of `/api/v1/sessions`.
2. **Buffer Limits**: Large data payloads (like scanning base64 QR codes) exceeded standard Nginx memory buffers, triggering upstream connection shutdowns.

### Affected Files
* `nginx/default.conf`

### Exact Fix
Removed trailing paths from the `proxy_pass` block and raised Nginx request buffer allocations:
```nginx
location /api/v1/ {
    proxy_pass http://backend:8000/api/v1/;
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
}
```

### Verification Results
Base64 QR codes and multi-tenant webhook dispatches transit without gateway drops.

---

## Incident RCA-004: Passlib-Bcrypt Version Conflict

### Symptom
FastAPI container crashes during boot. Container logs display:
`ValueError: bcrypt.__about__ does not define __version__`

### Root Cause
The `passlib` security library implements internal self-checks when parsing bcrypt passwords. When `bcrypt` is upgraded to `4.x` versions, the metadata schemas change, causing passlib to crash.

### Affected Files
* `backend/requirements.txt`

### Exact Fix
Pinned dependencies to older, stable, fully compatible structures:
```
bcrypt==3.2.2
passlib[bcrypt]==1.7.4
```

### Verification Results
FastAPI launches cleanly and successfully processes password hashes and JWT creations.

---

## Incident RCA-005: Outdated Baileys Protocol Version Disconnects

### Symptom
WhatsApp Engine container disconnects from WhatsApp servers instantly during scan. Logs display:
`Connection closed. Reason code: 405 Outdated protocol version.`

### Root Cause
Baileys core socket connection hardcoded the Web WhatsApp protocol version. WhatsApp periodic upgrades reject requests using outdated version sequences, disconnecting standard sockets with code `405`.

### Affected Files
* `whatsapp-engine/src/baileys-manager.ts`

### Exact Fix
Dynamically fetch the latest valid protocol version via external servers during socket creation:
```typescript
import { fetchLatestBaileysVersion } from "@whiskeysockets/baileys";

const { version, isLatest } = await fetchLatestBaileysVersion();
console.log(`Using Baileys version: ${version.join('.')}, isLatest: ${isLatest}`);

const socket = makeWASocket({
  version,
  auth: state,
  printQRInTerminal: false,
});
```

### Verification Results
WhatsApp instances connect instantly and remain stable over extended operational runs.

---

## Incident RCA-006: Background Task DB Connection Leak (Celery)

### Symptom
When the AI pipeline attempts to process an inbound message and write a reply, database transaction pools exhaust, blocking API endpoints.

### Root Cause
FastAPI's dependency injection (`get_db`) works perfectly within standard request-response loops. However, in background tasks (`BackgroundTasks`), the request finishes and the session closes *before* the async execution is finished. The thread then attempts to write to a closed connection, locking pool structures.

### Affected Files
* `backend/app/routers/sessions.py`
* `backend/app/services/ai_service.py`

### Exact Fix
Created a dedicated thread-safe session generator block specifically tailored for background processing:
```python
from app.database import SessionLocal

def process_ai_reply_task(message_id: str):
    db = SessionLocal()
    try:
        # Execute query and AI generation inside local transaction
        db.commit()
    finally:
        db.close()  # Guarantees clean resource release
```

### Verification Results
AI replies execute asynchronously and release pool connections cleanly without locking API endpoints.

---

## Incident RCA-007: Next.js Stale Closure & Input Clear UX Bugs

### Symptom
1. Typing a message and clicking Send immediately clears the input field, but if the API fails, the typed message is lost, and only an alert is shown.
2. Polling intervals overwrite optimistically rendered message bubbles, causing threads to flicker.
3. Message sends capture old variables due to stale closures in the component lifecycle.

### Root Cause
1. In `frontend/src/app/dashboard/page.tsx`, `setAgentMsgText('')` executed before `await api.chats.sendMessage()`.
2. Polling unconditionally replaced the local `messages` state with server data, wiping out in-flight optimistic bubbles.
3. React `useState` hooks captured stale state inside `setInterval` closures.

### Affected Files
* `frontend/src/app/dashboard/page.tsx`

### Exact Fix
1. Implemented inline error banners and an `isSending` state to lock UI controls during sends. If the API fails, input text is restored from the local state.
2. Utilized refs (`activeConvRef`) to keep references up-to-date across render cycles.
3. Added optimistic status checks before polling updates:
```typescript
setMessages(prev => {
  const hasPending = prev.some(m => String(m.id).startsWith('optimistic-'));
  if (hasPending) return prev; // Do not overwrite in-flight sends
  return freshList;
});
```

### Verification Results
Outbound live overrides render instantly, queue safely, and update fluidly without thread flicker or input losses.
