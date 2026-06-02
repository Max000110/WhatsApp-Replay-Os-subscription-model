# SYSTEM ARCHITECTURE FORENSICS — ReplyOS
**Date of Forensic Acquisition**: 2026-05-30T15:30:00+05:30  
**Security Boundary Status**: ACTIVE & REINFORCED  

---

## 1. Containerized Infrastructure Stack (8 Services)

The production environment consists of 8 highly isolated Docker containers operating on the Oracle Cloud VM (`144.24.126.153`):

| Container Name | Service Role | Image Source | Port Mapping (Host -> Container) | Health Check |
|---|---|---|---|---|
| `saas_nginx` | Reverse Proxy & Gateway Router | `whatsapp-ai-saas-nginx` | `8080 -> 80`, `8443 -> 443` | N/A |
| `saas_backend` | FastAPI Core Application API | `whatsapp-ai-saas-backend` | Internal Only (exposed via Nginx bridge) | Custom (FastAPI endpoint check) |
| `saas_frontend` | Next.js Customer & Admin UI | `whatsapp-ai-saas-frontend` | `30000 -> 3000` | N/A |
| `saas_whatsapp_engine` | Baileys Node.js Socket Manager | `whatsapp-ai-saas-whatsapp-engine` | `3000 -> 3000` | N/A |
| `saas_worker` | Celery Background Job Processor | `whatsapp-ai-saas-worker` | Internal Only | Celery Inspect ping |
| `saas_redis` | Cache, Message Broker, Blacklist | `redis:7-alpine` | Internal Only (port 6379) | `redis-cli ping` |
| `saas_postgres` | Relational DB & Vector Store | `pgvector/pgvector:pg16` | Internal Only (port 5432) | `pg_isready` check |
| `saas_ollama` | Local LLM Inference Service | `ollama/ollama:latest` | `11434 -> 11434` | N/A |

---

## 2. Network Topology & Gateway Configuration

The containers communicate over an isolated Docker bridge network `whatsapp-ai-saas_default`. 

### Nginx Reverse Proxy (`saas_nginx`) Routing Flow:
* **Host Port `8080` (HTTP)** is mapped to Nginx port `80`.
* **Dynamic Upstream Name Resolution**: Nginx employs Docker's internal DNS (`127.0.0.11`) with a 5-second TTL cache (`resolver 127.0.0.11 valid=5s;`) to dynamically resolve backend and frontend container IP addresses on container rebuilds, neutralizing stale cache 502 Bad Gateway errors.
* **Frontend Routing**: All requests to `/` and client routes are proxied to `http://frontend:3000` with WebSocket upgrade parameters enabled.
* **API Backend Routing**: Requests to `/api/v1` are rate-limited (`limit_req_zone` at 10 requests/sec with burst = 20) and forwarded to `http://backend:8000/api/v1`. The connection read timeout is expanded to `3600s` to maintain open WebSocket tunnels for live-chat client events.
* **Security Headers**:
  - `Strict-Transport-Security`: Enforces HTTPS for client browsers.
  - `X-Frame-Options: SAMEORIGIN`: Safeguards against Clickjacking attacks.
  - `X-Content-Type-Options: nosniff`: Mitigates MIME sniffing.
  - `Content-Security-Policy`: Strictly governs dynamic scripts, styles, frames, and asset origins.

---

## 3. Backend Routing & Endpoint Architecture

The FastAPI backend exposes the following endpoint routing groups under the `/api/v1` namespace:

1. **`/auth`** (`app/auth/router.py`):
   * `POST /login`: Validates tenant member credentials; generates standard user JWT. Enforces role boundary checks, blocking users with `role == 'admin'`.
   * `POST /register`: Onboards new tenants.
2. **`/sessions`** (`app/routers/sessions.py`):
   * `GET /`, `POST /`: Lists and initiates WhatsApp engine pairing sessions.
   * `POST /webhook`: Inbound WhatsApp event handler (messages, statuses, socket updates).
3. **`/bots`** (`app/routers/bots.py`):
   * `GET /`, `POST /`, `PATCH /{id}`, `DELETE /{id}`: Manages tenant chatbot personalities, configurations, and vector scopes.
   * `POST /{id}/test-prompt`: Prompt Sandbox dry-run console for testing customized business brains.
4. **`/chats`** (`app/routers/chats.py`):
   * `GET /`: Lists all active customer conversations.
   * `GET /{id}/messages`: Hydrates messaging threads.
   * `POST /send`: Manual "Live Override" agent message dispatches.
   * `DELETE /{id}`: Archive/hard delete chat thread (triggers Redis AntiBanQueue purging via ephemerals).
5. **`/knowledge`** (`app/routers/knowledge.py`):
   * `GET /`, `POST /`: Custom RAG Knowledge Base indexing.
   * `POST /{kb_id}/documents`: PDF/TXT vectorization indexer.
6. **`/campaigns`** (`app/routers/campaigns.py`):
   * `GET /`, `POST /`: Marketing broadcast scheduling.
7. **`/admin`** (`app/routers/admin.py`):
   * `POST /auth/login`: Super Admin authentication endpoint.
   * `GET /tenants`: Lists all SaaS tenants and telemetry indices.
   * `POST /tenants/{id}/suspend` / `reactivate`: Restricts / restores tenant subscription scopes and user states.
   * `POST /tenants/{id}/force-logout`: Instantly invalidates user access.
   * `DELETE /tenants/{id}/purge`: Secure hard delete of all DB data and vector indices.
   * `POST /system/emergency-lock` / `unlock`: Global kill-switch blocking all non-admin logins and API requests.

---

## 4. Redis Architecture & Command Queues

Redis (`saas_redis`) acts as the high-throughput synchronization engine. The workspace uses `SecretRedisPassword123!` to lock external interface scans:

1. **Celery Task Broker**: Handles background job queues for large marketing campaign dispatches and document parsing.
2. **Outbound Anti-Ban Delay Queue (`AntiBanQueue`)**: 
   * Outbound WhatsApp engine dispatches are held in Redis lists: `whatsapp_queue_{session_id}`.
   * Engine workers pop messages and apply simulated human delays (2 to 5 seconds).
3. **Session Revocation Blacklist**: 
   * Active admin blacklists are stored under `blacklist_token:{token}` keys.
   * Expired JWTs are queried against Redis on every admin route call.
4. **Mid-Flight Abort Lock (`deleted_chat:{session_id}:{customer_phone}`)**:
   * Set when a conversation is deleted or archived.
   * Queried by the Node.js engine during Anti-Ban delays; blocks sending if the thread was recently deleted.
5. **Global System Emergency Lock (`emergency_system_lock`)**:
   * Evaluated by FastAPI auth middleware. If `true`, restricts access to `/api/v1/*` routes for all client-level users.

---

## 5. PostgreSQL & pgvector Schema Layout

Postgre (`saas_postgres`) stores relational state under database `saas_whatsapp`. The custom PostgreSQL container is configured with `pgvector` for similarity calculations:

* **Core Tables**:
  - `tenants`: Stores tenant metadata, subdomains, registration parameters, and delivery country configurations (`default_country_code`).
  - `users`: Standard user entries with password hashes, roles (`owner`, `agent`, `admin`), and active flags (`is_active`).
  - `conversations`: Active WhatsApp threads normalized by JID, tracking bot pause states (`bot_paused_until`), and short summaries.
  - `messages`: Standard logs of all messages, tracking `whatsapp_message_id`, `client_uuid`, `origin`, and ACK status states.
  - `whatsapp_sessions`: Pairings and status states of Baileys sessions.
  - `chatbots`: Settings for isolated AI prompts, brand guides, services catalogs, product descriptions, pricing rules, and safety thresholds.
  - `subscriptions`: Tracking current tiers (`free`, `starter`, `pro`, `agency`), counters, limiters, and Razorpay links.
  - `audit_logs`: Detailed immutable security tracks of all admin command sequences.

---

## 6. WhatsApp Baileys Engine Architecture

The `saas_whatsapp_engine` acts as the low-level transport layer:
* Implemented as a Node.js companion service wrapping the `@whiskeysockets/baileys` library.
* Couples with the backend using one-shot HTTP webhooks to notify FastAPI of inbound chat events, outgoing message status callbacks (ACK states: `sent`, `delivered`, `read`), and socket terminations.
* Integrates `AntiBanQueue` logic directly with Redis to throttle message output speeds.

---

## 7. Authentication & Boundary Protection Matrix

ReplyOS enforces strict dual-isolation domains between Super Administrators and Tenant Users:

```
                  ┌──────────────────────┐
                  │   Client Router      │
                  │   /login             │
                  └──────────┬───────────┘
                             │
                             ▼
                    [ /auth/login ]
            Is User.role == 'admin'? (HTTP 403)
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Tenant Portal       │
                  │  (saas_token)        │
                  │  Scopes: Standard    │
                  └──────────────────────┘

                  ┌──────────────────────┐
                  │   Admin Router       │
                  │   /admin/login       │
                  └──────────┬───────────┘
                             │
                             ▼
                 [ /admin/auth/login ]
           Enforces User.role == 'admin' (HTTP 401)
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Super Admin Panel   │
                  │  (replyos_admin_token)│
                  │  Scopes: super_admin │
                  └──────────────────────┘
```

* **Client Security Separation**: The client portal `/dashboard` has no admin imports, actions, or views. Administrative routes at `/admin` require JWT tokens bearing the custom scope `super_admin`.
* **Administrative Safeguard Protection**: Super Admin accounts (`role == "admin"`) are globally exempt from deactivation workflows inside `suspend_tenant`, `terminate_tenant`, `force_logout_users`, and `revoke_tenant_access`.
* **Administrative Tenant Lockout Prevention**: The critical `System Operations` tenant is explicitly locked against administrative actions (`suspend`, `terminate`, `purge`, `force_logout`, `revoke_access`).
