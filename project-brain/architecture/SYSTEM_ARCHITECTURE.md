# System Architecture — ReplyOS WhatsApp SaaS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## Core Stack Overview

```
Browser (Customer / Super Admin)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│              Nginx Reverse Proxy (Port 8080)            │
│  server_name: localhost 144.24.126.153                  │
│  /          → frontend:3000                             │
│  /api/v1    → backend:8000                              │
│  /ws        → backend:8000 (WebSocket upgrade)          │
└─────────────────────────────────────────────────────────┘
        │                               │
        ▼                               ▼
┌──────────────────┐          ┌──────────────────────┐
│  Next.js Frontend│          │  FastAPI Backend      │
│  (saas_frontend) │          │  (saas_backend)       │
│  Port 3000       │          │  Port 8000            │
│  Routes:         │          │  /api/v1/auth         │
│  /               │          │  /api/v1/sessions     │
│  /login          │          │  /api/v1/chats        │
│  /dashboard      │          │  /api/v1/campaigns    │
│  /admin/login    │          │  /api/v1/billing      │
│  /admin          │          │  /api/v1/admin        │
└──────────────────┘          │  /api/v1/ws           │
                               └──────────────────────┘
                                         │
                    ┌────────────────────┼────────────────┐
                    ▼                    ▼                ▼
           ┌──────────────┐    ┌──────────────┐  ┌──────────────┐
           │  PostgreSQL  │    │    Redis     │  │  WhatsApp    │
           │  (postgres)  │    │  (redis)     │  │  Engine      │
           │  Port 5432   │    │  Port 6379   │  │  (baileys)   │
           │              │    │  - PubSub    │  │  Port 3000   │
           │  - tenants   │    │  - Sessions  │  │              │
           │  - users     │    │  - Rate Limit│  │  - Baileys   │
           │  - convs     │    │  - WA Queues │  │    MD Proto  │
           │  - messages  │    │  - Celery    │  │  - AES-256   │
           │  - sessions  │    │    Broker    │  │    Auth      │
           │  - chatbots  │    └──────────────┘  └──────────────┘
           │  - campaigns │              │
           │  - billing   │              ▼
           │  - audit_logs│    ┌──────────────┐
           └──────────────┘    │  Celery      │
                               │  Worker      │
                               │  (worker)    │
                               │              │
                               │  - Campaign  │
                               │    Broadcast │
                               │  - Sub Expiry│
                               │  - Renewal   │
                               │  - Grace     │
                               │    Period    │
                               └──────────────┘
                                         │
                                         ▼
                               ┌──────────────┐
                               │  Ollama LLM  │
                               │  (ollama)    │
                               │  Port 11434  │
                               │              │
                               │  qwen2.5:    │
                               │  1.5b-instr  │
                               └──────────────┘
```

---

## Authentication Architecture

### Customer Authentication
- **Login**: `POST /api/v1/auth/login` → JWT signed with `SECRET_KEY`
- **Token Storage**: `localStorage['saas_token']`
- **Scopes**: Standard user scopes
- **Guards**: `Depends(get_current_user)` — validates JWT + checks tenant active status

### Super Admin Authentication
- **Login**: `POST /api/v1/admin/auth/login` → 3-phase flow
  - Phase 1: Credentials → may force password rotation
  - Phase 2: TOTP 2FA if enabled
  - Phase 3: Final JWT with `scopes: ["super_admin"]`, `totp_verified: True`
- **Token Storage**: `localStorage['replyos_admin_token']`
- **Guards**: `Depends(get_current_super_admin)` — validates scope + totp_verified

---

## Multi-Tenant Data Model

```
Tenant (saas_owner workspace)
├── Users (multiple users per tenant)
├── WhatsApp Sessions (multiple WhatsApp numbers per tenant)
│   └── Chatbots (one active bot per session)
├── Conversations (per customer JID, per session)
│   └── Messages (inbound/outbound per conversation)
├── Knowledge Bases (for RAG)
│   └── KB Documents
├── Campaigns (scheduled bulk sends)
│   └── Campaign Logs (per recipient)
├── Subscriptions (billing plan per tenant)
└── Payment Transactions (Razorpay order history)
```

---

## Message Flow Architecture

### Inbound (Customer → WhatsApp → System)
```
WhatsApp Network
    → Baileys MD Socket
    → baileys-manager.ts (normalize JID, strip companion suffix)
    → POST /api/v1/sessions/webhook (FastAPI)
    → Idempotency check (whatsapp_message_id)
    → normalize_jid() → find/create conversation
    → Store message (status: "read")
    → Subscription check → Monthly limit check → Bot pause check
    → Fetch chatbot → RAG context → Ollama inference
    → Queue outbound bot reply → Redis PubSub → WebSocket broadcast
```

### Outbound (Agent/Bot → WhatsApp)
```
FastAPI (chats.py / sessions.py / tasks.py)
    → normalize_jid() validation
    → Insert message (status: "queued")
    → Redis PubSub → WebSocket broadcast (status: "queued")
    → session_service.send_whatsapp_message()
    → HTTP POST whatsapp-engine:3000/sessions/send
    → anti-ban.ts AntiBanQueue (validate JID format)
    → Typing simulation + safety jitter
    → socket.sendMessage() → Baileys → WhatsApp Network
    → ACK webhook → FastAPI → DB update → Redis PubSub → WS broadcast
```

---

## Subscription Plan Hierarchy

| Tier | Monthly Messages | Concurrent Sessions | Bots | Price |
|---|---|---|---|---|
| Free | 100 | 1 | 1 | ₹0 |
| Starter | 1,000 | 2 | 2 | ₹999 |
| Pro | 10,000 | 5 | 5 | ₹2,999 |
| Agency | 100,000 | 20 | 20 | ₹9,999 |

---

## Security Architecture

- **JWT**: HS256 signed, 2h expiry for customers, 2h for admin
- **Rate Limiting**: Redis sliding window, progressive ban keys `ip_ban:{ip}`
- **Razorpay**: HMAC-SHA256 signature verification on all payment events
- **Baileys Sessions**: AES-256-GCM encrypted in PostgreSQL
- **Nginx**: HSTS, X-Frame-Options, X-Content-Type-Options, CSP headers
- **Admin**: Brute-force lockout with Redis counter keys, TOTP 2FA

---

## Deployment Configuration

- **Host**: Oracle Cloud VM, Ubuntu
- **Public IP**: `144.24.126.153`
- **External Port**: `8080` (Nginx)
- **Internal Network**: Docker Compose `saas_network` bridge
- **Environment**: `.env` file injected via Docker Compose
- **Redis Auth**: None (internal network only, not publicly exposed)
- **Payment Mode**: `PAYMENT_MODE=test` (Razorpay test mode active)
