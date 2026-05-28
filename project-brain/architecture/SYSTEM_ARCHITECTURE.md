# System Architecture & Engineering Blueprint

This document details the multi-tenant design, database schemas, message pipelines, and data scoping mechanisms of ReplyOS.

---

## 1. Microservices Container Topology

The platform is orchestrating 8 isolated dockerized services running on a shared bridge virtual network:

```
                      +-----------------------------+
                      |      Nginx Gateway Proxy    |
                      +--------------+--------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v (/api/v1/*)                                   v (/*)
+------------+------------+                     +------------+------------+
|   FastAPI Backend API   |                     |     Next.js Frontend    |
+------------+------------+                     +-------------------------+
             |
     +-------+-------+-----------------------+
     |               |                       |
     v               v                       v
+----+----+    +-----+-----+           +-----+-----+
|  Redis  |    | Postgres  |           | WhatsApp  |
|  Broker |    | Database  |           |  Engine   |
+----+----+    +-----+-----+           +-----+-----+
     ^               ^                       |
     |               |                       | (Webhook notifications)
     +--------+------+-----------------------+
              |
              v
       +------+------+
       |   Celery    | <=====================> Ollama (Local AI Inference)
       |   Worker    |
       +-------------+
```

### Inner Bridge Port Configurations
*   **`nginx`**: Exposes host Port `8080` (HTTP) and `8443` (HTTPS).
*   **`frontend`**: Next.js Node app, runs internally on port `3000`, exposed to host on `30000`.
*   **`backend`**: FastAPI ASGI app (Uvicorn), runs internally on port `8000`.
*   **`whatsapp-engine`**: Node Express app, runs internally on port `3000`.
*   **`postgres`**: PostgreSQL 16 + pgvector, runs internally on port `5432`.
*   **`redis`**: Redis Alpine, runs internally on port `6379`.
*   **`ollama`**: Runs on port `11434` for local CPU GGUF models compilation.

---

## 2. Relational Database Schema (DDL Models)

### Core Multi-Tenant & Message Tables
*   **`tenants`**: Scopes SaaS workspace directories.
*   **`users`**: Contains encrypted logins. Supports role fields (`owner`, `admin`, `member`).
*   **`subscriptions`**: Tracks active billing tiers (`free`, `starter`, `pro`, `agency`), subscription statuses (`active`, `expired`, `suspended`), current periods, and payment provider order/payment/subscription hashes.
*   **`whatsapp_sessions`**: Caches stateless credentials buffers for Baileys, connection statuses, and phone metadata.
*   **`conversations`**: Tracks customer phone normalizations and bot takeover durations (`bot_paused_until`).
*   **`messages`**: Persists text logs, sender classifications (`customer`, `user`, `bot`), delivery status ACKs, and client-generated UUID values.

### Extended SaaS Billing Tables
*   **`subscription_events`**: Chronological events catalog storing billing payloads.
*   **`payment_transactions`**: Razorpay transaction statuses (`created`, `captured`, `failed`).
*   **`tenant_quotas`**: Hard quota allocations (`max_bots`, `max_messages`, `messages_used`).
*   **`usage_metrics`**: Token consumption and outbound message count meters.
*   **`billing_history`**: SaaS invoice records.
*   **`autopay_tokens`**: Razorpay recurring auto-pay tokens.
*   **`renewal_jobs`**: Scheduled cron-like job tracking for auto-renewals.

---

## 3. Realtime Messaging Pipeline

```
[Customer Mobile]
       │ (Sends WhatsApp Message)
       ▼
[WhatsApp Servers]
       │
       ▼ (Baileys WebSocket Connection)
[WhatsApp Engine (Express)]
       │
       ▼ (Webhook POST /sessions/webhook)
[FastAPI Backend sessions.py] ──> Commits Inbound Message as 'read'
       │
       ▼ (FastAPI Background Task -> process_incoming_chat_pipeline)
[AI Chatbot Generation (Ollama)] ──> Queries RAG pgvector similarity
       │
       ▼ (POST /sessions/send)
[WhatsApp Engine anti-ban.ts] ──> Simulates composing indicator & queue delays
       │
       ▼ (Socket Outbound Send)
[Customer Mobile]
```

---

## 4. Quota Enforcement & Middleware

Every request that triggers an outbound message (Live override, campaigns, AI auto-replies) is intercepted by the billing check guards:
1. **Subscription Status Validation**: Resolves the tenant's plan. If status is `expired` or `suspended`, the dispatch is immediately rejected.
2. **Quota Checks**: Verifies monthly usage logs. If `messages_used` exceeds `max_messages_per_month` (e.g. 500 for Free tier), the system halts execution.
3. **Session Restrictions**: Blocks new session instantiations if the count of existing sessions exceeds the tier's `max_bots` allowance.
