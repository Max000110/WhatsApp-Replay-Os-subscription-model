# ReplyOS — Fixed Bugs Registry

This document catalogues the historical bug fixes and stabilization actions executed on the ReplyOS WhatsApp SaaS platform.

---

## 1. Resolved Bug Registry

### BUG-101 — Missing `psutil` System Dependency
* **Symptom**: Super Admin panel returned `502 Server Error`, rendering 0 tenants and all services offline.
* **Root Cause**: The diagnostics endpoint `get_system_health()` imported `psutil` which was missing from the backend container's `requirements.txt`. Uvicorn crashed with a `ModuleNotFoundError`.
* **Fix**: Added `psutil==5.9.8` to `backend/requirements.txt` and rebuilt images.
* **Result**: ✅ Verified system gauges and registry hydrate dynamically.

### BUG-102 — Docker Log File Descriptor Lockups
* **Symptom**: After host-level truncation of log files, login attempts hung and returned `502 Bad Gateway`.
* **Root Cause**: Truncating active container log files (`*-json.log`) directly on the host VM broke the Docker daemon's log file handles. Uvicorn threads calling the Docker socket hung waiting for standard output flushes.
* **Fix**: Executed a clean restart of the Docker container stack to re-register clean stdout/stderr log handles.
* **Result**: ✅ Verified Nginx and backend API return 200 OK immediately.

### BUG-103 — Authentication Cross-Login Leak (INC-014)
* **Symptom**: Super Admin credentials (`admin@replyos.com`) were accepted at the customer `/login` portal, generating customer-scoped sessions.
* **Root Cause**: The customer login handler `/auth/login` validated passwords but lacked user role assertions.
* **Fix**: Patched `backend/app/auth/router.py` to check `user.role` on validation. If `role == "admin"`, it raises `403 Forbidden`.
* **Result**: ✅ API successfully blocks admin logins at tenant portals.

### BUG-104 — Admin UI Component Leak in Dashboard (INC-015)
* **Symptom**: Normal tenant users setting `saas_role = 'admin'` in browser localStorage could see the Master Admin panel.
* **Root Cause**: The client-side dashboard page (`dashboard/page.tsx`) contained inline JSX structures, states, and action triggers for admin diagnostic endpoints.
* **Fix**: Gutted all admin components, variables, and menus from `dashboard/page.tsx`, isolating admin logic to `/admin` (`admin/page.tsx`).
* **Result**: ✅ Customer dashboard compiles cleanly and isolates user sessions.

### BUG-105 — False-Alarm Red Indicators on Sockets
* **Symptom**: Admin panel diagnostics displayed WebSocket status as RED/OFFLINE when active connections were 0.
* **Root Cause**: The rendering template treated connection counts of 0 as an offline state.
* **Fix**: Refactored the UI to handle the `"degraded"` state, rendering WebSocket status as an AMBER warning check if uvicorn is online but has 0 connections.
* **Result**: ✅ Verified UI displays warning indicator rather than critical offline indicators.

### BUG-106 — Outbound Blockages on International/LID targets
* **Symptom**: Outbound messages and chatbot replies sent to groups, international numbers, or 15-digit LID JIDs failed to send.
* **Root Cause**: The anti-ban queue regex in the Node engine was restricted to Indian numbers: `/^91[6-9]\d{9}@s\.whatsapp\.net$/`.
* **Fix**: Widened regex inside `anti-ban.ts` to `/^\d{7,20}@(s\.whatsapp\.net|lid|g\.us)$/` and rebuilt.
* **Result**: ✅ Verified manual overrides and chatbot responses dispatch to international/LID numbers successfully.

### BUG-107 — LID JID Normalization Webhook Bug
* **Symptom**: Live overrides and chatbot responses to users with WhatsApp Line Identities (LIDs) failed to deliver, staying in `sent` status indefinitely.
* **Root Cause**: Webhook receiver resolved JID using domain-stripped `from` key rather than `rawRemoteJid`, causing LID JIDs to normalize to `@s.whatsapp.net` instead of `@lid`.
* **Fix**: Patched `process_incoming_chat_pipeline` in `sessions.py` to prioritize `rawRemoteJid` if present.
* **Result**: ✅ Mocked inbound LID message; verified conversation JID was created correctly as `185654373789739@lid`, and live override dispatch succeeded.

### BUG-108 — AntiBanQueue Reboot Startup Drain Bug
* **Symptom**: Messages queued in Redis outbound queue stayed stuck after container reboot until a new message was sent.
* **Root Cause**: `AntiBanQueue` constructor initialized Redis connection but did not trigger queue worker. The queue worker was only triggered in `queueMessage()`.
* **Fix**: Triggered `this.triggerQueueWorker()` in Redis connect `then` callback in `anti-ban.ts` constructor to automatically drain pending messages on boot.
* **Result**: ✅ Verified clean container startup successfully drains Redis queues.

### BUG-109 — Google OAuth URL Parameter Malformation (HTTP 400)
* **Symptom**: Initiating Google Sign-In returned a `400 Bad Request` or malformed request error loop on the authentic Google Account picker popup.
* **Root Cause**: Next.js login buttons constructed the authorization URL using concatenated string templates which induced double URL encoding and spacing serialization conflicts for scopes.
* **Fix**: Re-engineered `handleGoogleLogin` and `handleAdminGoogleLogin` using native browser `URLSearchParams` standard arrays to dynamically build and serialize parameter queries.
* **Result**: ✅ Verified correct %20 scope spacing and verified seamless Google Consent popup redirection loop.

