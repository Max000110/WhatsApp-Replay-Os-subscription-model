# Project State & Single Source of Truth

**SaaS Platform**: ReplyOS - Multi-Tenant WhatsApp AI Automation & Billing Platform  
**Target Host VM IP**: `144.24.126.153`  
**Host Gateway Ports**: `8080` (Nginx Gateway), `30000` (Direct Next.js SSR)  
**Database**: PostgreSQL 16 + `pgvector` (Multi-tenant partition schemas)  
**Broker & Cache**: Redis 7 (Alpine container)  
**WhatsApp Emulation Engine**: Node.js `@whiskeysockets/baileys`  
**AI Inference**: Ollama Local (Qwen 2.5 + MiniLM Embeddings)  

---

## 1. Subsystem Configuration Matrix

| Subsystem | Production Status | Core Details |
| :--- | :--- | :--- |
| **Authentication** | ✅ Verified Active | JWT bearer tokens with embedded `tenant_id` scopes. User logins fully verified. |
| **WhatsApp Connection** | ✅ Verified Active | Stateless database creds persistence. Auto-fetches latest WhatsApp Web protocol versions. |
| **WebSocket Broadcast** | ✅ Verified Active | Streaming live events (`message`, `message_status`, `session`) through Nginx proxy. |
| **Live Chat Override** | ✅ Verified Active | Injects agent replies. Pauses AI chatbot automation for 15-minute windows on response. |
| **AI Reply Pipeline** | ✅ Verified Active | Background task reads webhook message events, queries Ollama, and dispatches via engine. |
| **Billing & Payments** | ⚠️ Production Hardened | Real Razorpay payment order creation and signature verify. Removed mock gateways. |
| **Super Admin Console** | ⚠️ Route Active | Super admin dashboard routers mounted at `/api/v1/admin/*` for global tenant/metric checks. |
| **Quota Enforcement** | ⚠️ Active check | Dynamic limits verified: Free (1 bot, 500 msg), Starter (2/5k), Pro (5/50k), Agency (20/1M). |

---

## 2. Dynamic Quota Enforcement

All key SaaS operations are locked behind subscription limits and expirations. If a tenant's subscription expires or is suspended:
*   Outbound live override messages are blocked (raises `402 Payment Required`).
*   New WhatsApp session instantiations are blocked (raises `402 Payment Required`).
*   Inbound AI auto-replies are bypassed (logs notice and returns without dispatching).
*   Marketing campaign broadcasts are paused automatically.

---

## 3. Realtime Event Deduplication

Race conditions between API promise resolutions and WebSocket `messages.upsert` updates are handled via Map-based deduplication key caches on the Next.js client.
Every message update is scoped by unique message IDs (using client-generated UUID keys passed to backend and returned in payloads).

---

## 4. Systems Status Telemetry

* **WebSocket Gateway**: **OPERATIONAL** (Nginx correctly terminates HTTP/HTTPS and forwards Websocket streams via standard headers).
* **Campaign Broadcaster**: **IDLE** (Processes schedules asynchronously using Celery worker dispatches).
* **AI Bot Engine**: **ACTIVE** (Directs message events to Ollama generator via FastAPI ASGI background tasks).
* **Razorpay Production Router**: **ACTIVE** (Secure HMAC SHA256 verification of capture signatures).
* **Super Admin System**: **ACTIVE** (Enforces strict `role == 'admin'` claims check on all administrative operations).
