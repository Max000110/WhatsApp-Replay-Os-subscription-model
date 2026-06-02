# ReplyOS — Feature Registry

This document records the complete functional registry of the ReplyOS Multi-Tenant WhatsApp AI SaaS platform, mapping frontend paths, API endpoints, and database models.

---

## 1. Customer Tenant Features

### 1.1 Multi-Tenant Dashboard (`/dashboard`)
* **Purpose**: Allows tenant owners and members to monitor chat activity, scan WhatsApp session QR codes, and review chatbot auto-reply stats.
* **Backend Source**: `backend/app/routers/chats.py` and `backend/app/routers/sessions.py`.
* **Database Models**: `Tenant`, `User`, `Conversation`, `Message`.
* **Status**: ✅ Operational (Complete isolation from Super Admin views).

### 1.2 WhatsApp Session Manager (`/dashboard` - Sessions Tab)
* **Purpose**: Manages multi-device Baileys connections. Displays real-time connection status, phone numbers, and raw QR codes.
* **Backend Source**: `backend/app/routers/sessions.py` (FastAPI) and `whatsapp-engine/` (Node.js companion).
* **Database Models**: `WhatsAppSession`.
* **Status**: ✅ Operational (Supports auto-reconnection and state encryption).

### 1.3 Campaign Scheduler (`/dashboard` - Campaigns Tab)
* **Purpose**: Coordinates timezone-aware marketing broadcasts. Supports custom delays, throttling, and logs delivery success metrics.
* **Backend Source**: `backend/app/routers/campaigns.py` and `backend/app/worker/celery_app.py`.
* **Database Models**: `Campaign`, `CampaignLog`.
* **Status**: ✅ Operational.

### 1.4 Live Agent Override & Chat (`/dashboard` - Chat Tab)
* **Purpose**: WebSockets-driven chat interface allowing human agents to intercept conversations, pause chatbot auto-replies, and send messages manually.
* **Backend Source**: `backend/app/routers/chats.py` and `backend/app/routers/websockets.py`.
* **Database Models**: `Conversation`, `Message`.
* **Status**: ✅ Operational.

### 1.5 Subscription & Razorpay Checkout (`/dashboard` - Billing Tab)
* **Purpose**: Handles plan upgrades/downgrades (`free`, `starter`, `pro`, `agency`) with Razorpay checkout flow, invoicing, and subscription renewals.
* **Backend Source**: `backend/app/routers/billing.py`.
* **Database Models**: `Subscription`, `BillingHistory`.
* **Status**: ✅ Operational.

### 1.6 RAG Knowledge Base (`/dashboard` - AI Training Tab)
* **Purpose**: Documents upload center (PDF, text) with vector embedding chunks stored in Postgres `pgvector` for context-injected AI chat replies.
* **Backend Source**: `backend/app/routers/knowledge.py` and `backend/app/services/ai_service.py`.
* **Database Models**: `KnowledgeBase`, `KBDocument`, `KBDocumentChunk`.
* **Status**: ✅ Operational.

---

## 2. Super Admin Control Plane (`/admin`)

### 2.1 Tenant Lifecycle Registry (Tab 1)
* **Purpose**: Registry of all platform tenants. Allows plans overrides, quota audits, and active suspension triggers.
* **Backend Source**: `backend/app/routers/admin.py::get_tenants()`.
* **Status**: ✅ Operational.

### 2.2 System Real-time Diagnostics (Tab 2)
* **Purpose**: Dynamic monitoring of host CPU/RAM/Disk and service connections (PostgreSQL ping, Redis latency, Celery inspector, Ollama, Node sockets).
* **Backend Source**: `backend/app/routers/admin.py::get_system_health()`.
* **Status**: ✅ Operational.

### 2.3 Permanent Administrative Audit Trail (Tab 3)
* **Purpose**: Read-only tracking of administrative actions, targets, and JSON state traces.
* **Backend Source**: `backend/app/routers/admin.py::get_audit_logs()`.
* **Database Models**: `AuditLog`.
* **Status**: ✅ Operational.

### 2.4 Control Plane Hardening & 2FA (Tab 4)
* **Purpose**: Controls MFA/TOTP activations, generates QR codes, displays recovery tokens, and initiates maintenance broadcasts.
* **Backend Source**: `backend/app/routers/admin.py` (TOTP handlers).
* **Status**: ✅ Operational.

### 2.5 Platform Emergency Circuit Breaker (Tab 4 - Maintenance)
* **Purpose**: Redis-backed global switch blocking non-admin authentication attempts and API calls with `503 Service Unavailable` during incidents.
* **Backend Source**: `backend/app/routers/admin.py::emergency_lock_system()`.
* **Status**: ✅ Operational.
