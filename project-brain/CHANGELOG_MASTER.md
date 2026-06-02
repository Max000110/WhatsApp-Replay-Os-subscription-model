# ReplyOS — Consolidated Master Changelog

This document tracks all completed engineering tasks, files changed, verification logs, and active operational risks.

---

## 1. Master Changelog Timeline

### 2026-05-28 — Platform Inception & Foundations
* **Task**: Initialized docker compose environments, postgres schemas, and Baileys WhatsApp sockets handlers.
* **Status**: ✅ Completed.
* **Files Changed**: `docker-compose.yml`, `backend/`, `frontend/`, `whatsapp-engine/`, `postgres-init/`.
* **Result**: Multi-tenant chatbot platform initialized.
* **Verification Evidence**: All 8 services successfully compile and register health status on host VM interface.

### 2026-05-28 — Webhook Idempotency & JID Formatting
* **Task**: Solved duplicate messages rendering in frontend client and database primary key conflicts.
* **Status**: ✅ Completed.
* **Files Changed**: `backend/app/routers/chats.py`, `backend/app/routers/sessions.py`, `backend/app/core/jid.py`.
* **Result**: Implemented idempotency validation before database writes and unique constraint on conversations.
* **Verification Evidence**: Checked that incoming webhook events retry without throwing duplicates.

### 2026-05-29 — Super Admin Control Plane
* **Task**: Created Super Admin operations portal, audit logging system, and MFA.
* **Status**: ✅ Completed.
* **Files Changed**: `backend/app/routers/admin.py`, `frontend/src/app/admin/page.tsx`, `frontend/src/app/admin/login/page.tsx`.
* **Result**: Deployed isolated admin router with TOTP verification and SQL-backed audit tracking.
* **Verification Evidence**: Successfully generated TOTP QR codes and logged admin actions transactionally.

### 2026-05-29 — Diagnostics & 502 Debugging
* **Task**: Solved Super Admin panel 502 error and diagnostics failing indicators.
* **Status**: ✅ Completed.
* **Files Changed**: `backend/requirements.txt`, `backend/app/routers/admin.py` (Celery heartbeat inspect).
* **Result**: Added missing `psutil` dependency to requirements and integrated dynamic Celery broker pings.
* **Verification Evidence**: Sockets status, Postgres, Redis, and Celery worker health gauges load correctly.

### 2026-05-29 — Security Boundary Hardening
* **Task**: Resolved cross-login auth boundary leak (INC-014) and customer dashboard admin tab visibility leak (INC-015).
* **Status**: ✅ Completed.
* **Files Changed**: `backend/app/auth/router.py`, `frontend/src/app/dashboard/page.tsx`.
* **Result**: Explicitly blocked users with role `"admin"` from customer login flow and gutted admin components from `/dashboard`.
* **Verification Evidence**: Customer dashboard loads 100% isolated, admin@replyos.com returns `403 Forbidden` at customer portals.

### 2026-05-29 — Safe Storage Cleanup & FD Stabilization
* **Task**: Executed VM storage cleanup (Phase 7) and solved resulting logging file descriptor lockups.
* **Status**: ✅ Completed.
* **Files Changed**: Host VM `/tmp` and log folders, `docker-compose.yml`.
* **Result**: Reclaimed **10.02 GB** of host storage and resolved the Bad Gateway 502 lockouts by restarting container stack processes.
* **Verification Evidence**: System health report displays disk utilization dropped from 27% to 20%. Login endpoint resolves successfully.

---

## 2. Active Risks & Coexistence
* **OLlama CPU Load spikes**: Multi-agent chat triggers concurrent inference threads on VM processors, causing temporary API latency. Ensure Celery rate limits chatbots to prevent VM lockups.
* **WhatsApp Session Status Delays**: Device status callbacks are carrier dependent. Add daemon cron checking for stale outbound message delivery receipts.
