# CURRENT STATE RECONSTRUCTION — ReplyOS Forensic Hardening Takeover

**Last Synchronized**: 2026-05-30T19:20:00+05:30  
**Takeover Lead**: Principal Staff Engineer, Principal SRE & SRE Incident Commander

---

## 1. Architecture Map

```
                                 ┌──────────────────────┐
                                 │    Nginx Gateway     │ (saas_nginx, Port 8080/8443)
                                 └──────────┬───────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
       ┌────────────────────────┐                      ┌────────────────────────┐
       │   Next.js Frontend     │ (saas_frontend)      │   FastAPI Backend Core │ (saas_backend)
       │   (Dashboard & UI)     │                      │   (REST & Websockets)  │
       └────────────────────────┘                      └────────────┬───────────┘
                                                                    │
                    ┌───────────────────────────────────────────────┼────────────────────────┐
                    │                                               │                        │
                    ▼                                               ▼                        ▼
       ┌────────────────────────┐                      ┌────────────────────────┐ ┌────────────────────┐
       │ WhatsApp Node.js Engine│ (saas_whatsapp_engine│   Celery Background    │ │ Local AI Inference │
       │ (Baileys client/sock)  │                      │   Workers (Tasks)      │ │ Service (Ollama)   │
       └────────────┬───────────┘                      └────────────┬───────────┘ └──────────┬─────────┘
                    │                                               │                        │
                    └───────────────────────┬───────────────────────┘                        │
                                            │                                                │
                                            ▼                                                │
                               ┌────────────────────────┐                                    │
                               │  Redis Message Broker  │ (saas_redis)                       │
                               │  (AntiBan & Queues)    │                                    │
                               └────────────┬───────────┘                                    │
                                            │                                                │
                                            └───────────────────────┼────────────────────────┘
                                                                    │
                                                                    ▼
                                                       ┌────────────────────────┐
                                                       │  PostgreSQL Database   │ (saas_postgres)
                                                       │  (with pgvector)       │
                                                       └────────────────────────┘
```

---

## 2. Database Relationships

The database system is powered by PostgreSQL + `pgvector` (`saas_postgres`):

```
 [tenants] 1 ──── 0..* [users]
    │ 1
    ├──────────── 0..* [whatsapp_sessions] 1 ── 0..* [conversations] 1 ── 0..* [messages]
    │ 1                                                                       │ 1..*
    ├──────────── 0..* [chatbots] ────────────────────────────────────────────┘
    │ 1
    ├──────────── 1 [subscriptions]
    │ 1
    └──────────── 0..* [audit_logs]
```

### Table Definitions & Foreign Key Constraints:
- **`tenants`**: Isolated SaaS accounts. Standard columns: `id` (UUID PK), `name`, `subdomain`, `status`, `data_retention_policy`, `termination_grace_period_ends`.
- **`users`**: Customer accounts & Super Admins. Foreign Key: `tenant_id` referencing `tenants.id` on delete CASCADE.
- **`subscriptions`**: Billing status and max quotas. Foreign Key: `tenant_id` referencing `tenants.id` on delete CASCADE.
- **`whatsapp_sessions`**: Baileys multi-device pairing tokens and socket credentials. Foreign Key: `tenant_id` referencing `tenants.id` on delete CASCADE.
- **`conversations`**: Dynamic messaging threads. Foreign Key: `tenant_id` referencing `tenants.id` on delete CASCADE. Unique constraint `uq_tenant_customer_phone` on `(tenant_id, customer_phone)`.
- **`messages`**: Persisted conversation messages. Foreign Key: `conversation_id` referencing `conversations.id` on delete CASCADE.
- **`kb_document_chunks`**: Vector pieces for RAG matching. Foreign Key: `document_id` referencing `kb_documents.id` on delete CASCADE. Embedding column uses `vector(384)`.
- **`audit_logs`**: Super Admin administrative trail. Foreign Key: `admin_user_id` referencing `users.id` nullable, `target_tenant_id` referencing `tenants.id` nullable on delete CASCADE.

---

## 3. Active Services

1. **`saas_nginx`**: SSL termination, path-based routing (Frontend `/` -> `saas_frontend`, API `/api/v1` -> `saas_backend`), and Nginx-level rate-limiting.
2. **`saas_backend`**: FastAPI framework serving as the REST API endpoints and live-chat event WebSocket gateway.
3. **`saas_frontend`**: React UI built in Next.js, providing Tenant and Admin management panels.
4. **`saas_whatsapp_engine`**: Node.js companion daemon wrapping `@whiskeysockets/baileys` to manage raw WebSocket connections to WhatsApp Web.
5. **`saas_worker`**: Celery worker consuming backend tasks (campaign broadcasts and PDF parsing).
6. **`saas_redis`**: Celery broker, token blacklist, rate limit storage, and humanized Anti-Ban queuing.
7. **`saas_postgres`**: Relational DB storage with `pgvector` extensions enabled.
8. **`saas_ollama`**: Local inference engine hosting `qwen2.5:1.5b-instruct` and `all-minilm` embedding models.

---

## 4. Active Features

- **Multi-Tenant Isolation**: Separation of users, bots, sessions, conversations, and KB assets.
- **WhatsApp Web Companion**: Baileys-driven multi-device QR-pairing and socket-level message delivery.
- **15-Layered AI Brain**: Structured prompt assembly merging business catalogs, pricing, hours, location, policies, and custom prompts.
- **pgvector-powered RAG**: Semantic vector lookups matching inbound queries to document chunks.
- **Anti-Ban Outbound Throttling**: Queue-based random delays (2-5s) preventing bulk message triggers.
- **Super Admin Control Plane**: Tenant suspension, reactivation, force logout, and transactional hard purges.
- **Billing & Subscriptions**: Mock payment checkouts and dynamic plan quota enforcement.
- **Emergency System Lock**: Complete API lockouts protecting endpoints during incidents.
- **Durable Webhook Queue**: Auto-retry queue protecting engine status dispatches against backend downtime.

---

## 5. Open Incidents

- **INCIDENT-A (AI Response Code Error 404)**: WhatsApp responded with `[AI Engine Response Code Error 404]` when misconfigured.
  - *Status*: ✅ RESOLVED & VERIFIED.
- **INCIDENT-B (Testing Sandbox Crash)**: Hydration exception on dashboard load.
  - *Status*: ✅ RESOLVED & VERIFIED.
- **INCIDENT-C (AI Brain Save Validation)**: Omitting `bot.policies` from prompt layers.
  - *Status*: ✅ RESOLVED & VERIFIED.
- **INCIDENT-D (Latency Forensics)**: Target latency < 5 seconds; CPU baseline was 9.4 seconds.
  - *Status*: ✅ OPTIMIZED & CACHED (Fast-path deflection).

---

## 6. Open Bugs

- **BUG-001 (Outbound status webhook losses)**: Stuck at "sent" on backend container downtime.
  - *Status*: ✅ RESOLVED & VERIFIED.
- **BUG-002 (International prepending)**: Normalization errors when numbers miss country codes.
  - *Status*: ✅ RESOLVED & VERIFIED.
- **BUG-003 (Ollama CPU Exhaustion)**: Heavy concurrent AI load spikes CPU.
  - *Status*: ⚠️ MITIGATED (Fast-path Deflect Cache and throttled worker threads).

---

## 7. Existing Fixes

- **Purge Relational Integrity**: Resolved FK violations on administrative tenant purges by setting `target_tenant_id = None` in audit logs prior to hard DB deletes.
- **Fast-Path Greeting Deflection**: Cached greeting checks bypassing Ollama parsing to resolve latency issues for initial contacts.
- **Dynamic Port Resolver**: Configured Nginx bridge using Docker internal DNS resolver with 5s cache TTL to resolve IP shifts on container rebuilds.

---

## 8. Existing Safeguards

- **Strict User Boundaries**: Blocked `role == 'admin'` from customer auth and non-admin routes.
- **Tenant Lockouts Protection**: Critical `System Operations` tenant is explicitly locked on the backend against deactivations, suspends, terminations, and purges.
- **Redis Token Blacklist**: Immutable memory block for invalidated admin sessions.
