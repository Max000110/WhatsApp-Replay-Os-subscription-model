# Super Admin Runtime Audit — ReplyOS
**Date**: 2026-05-29 | **Prepared by**: Principal Super Admin Control Plane Engineer

---

## 1. Executive Summary

This audit validates all administrative controls inside the Super Admin Control Plane. Each feature button has been audited from Frontend interaction to API requests, Backend processing, database writes, and WebSocket/UI refreshes.

---

## 2. Button-by-Button Flow Audits

### 2.1 [Edit Plan] Button
* **Flow**: Frontend Form → `POST /api/v1/admin/tenants/{id}/change-plan` → Backend DB Commit → UI Table Updates.
* **Backend Endpoint**: `change_plan_tier(tenant_id, payload)`
* **Database Commit**: Sets `subscriptions.plan_tier`, `max_bots`, and `max_messages_per_month`.
* **Runtime Verification**: Changed plan of tenant `db29142a` (afzal) to `starter`. Database verified: `plan_tier = starter, status = active`.

### 2.2 [Suspend] / [Reactivate] Toggle Buttons
* **Flow**: Frontend click Suspend/Reactivate → `POST /api/v1/admin/tenants/{id}/suspend` (or `/reactivate`) → Backend sets tenant status → UI state changes.
* **Backend Endpoints**: `suspend_tenant(tenant_id)` and `reactivate_tenant(tenant_id)`
* **Database Commit**: Updates `tenants.status` to `"suspended"` or `"active"`. Logs action to `audit_logs`.
* **Runtime Verification**: Suspended and reactivated tenant `afzal`. Postgres query confirmed `status` transitioned to `active`.

### 2.3 [Archive] (Retention Policy Selector)
* **Flow**: Dropdown select Policy → `POST /api/v1/admin/tenants/{id}/retention-policy` → DB update → UI state sync.
* **Backend Endpoint**: `set_retention_policy(tenant_id, payload)`
* **Database Commit**: Updates `tenants.data_retention_policy` to `"archive"`, `"purge"`, or `"none"`.
* **Runtime Verification**: Commits policy option correctly. Verified via postgres: `data_retention_policy = archive` across all active tenants.

### 2.4 [Reset Counters] Button
* **Flow**: Click Reset → `POST /api/v1/admin/tenants/{id}/reset-counters` → Backend resets metrics → UI usage indicator shows 0.
* **Backend Endpoint**: `reset_usage_counters(tenant_id)`
* **Database Commit**: Resets `usage_metrics.message_count` and `usage_metrics.token_count` to `0` for the current month.
* **Runtime Verification**: Invoked reset. Verified usage metrics successfully updated.

### 2.5 [Disconnect Session] Button
* **Flow**: Click Disconnect → `POST /api/v1/admin/tenants/{id}/revoke-sessions` → WA Engine shutdown callback → UI session card displays Offline.
* **Backend Endpoint**: `force_revoke_tenant_sessions(tenant_id)`
* **WhatsApp Engine Action**: Node engine closes the active socket connection and cleans up session instances.
* **Runtime Verification**: Disconnected sessions are updated to `disconnected` in database table `whatsapp_sessions`.

### 2.6 [Quota Override] Settings
* **Flow**: Submit Quotas Form → `POST /api/v1/admin/tenants/{id}/quotas` → DB quota update → UI limits refresh.
* **Backend Endpoint**: `override_quotas(tenant_id, payload)`
* **Database Commit**: Inserts or updates `tenant_quotas` table fields `max_bots` and `max_messages`.
* **Runtime Verification**: Set quota limits for test tenants. Database confirmed quota overrides.

### 2.7 [Diagnostics] Panel
* **Flow**: Admin logs in → `GET /api/v1/admin/system-health` and `GET /api/v1/admin/storage-report` → UI Gauges hydrate.
* **Backend Endpoints**: `get_system_health()` and `get_storage_report()`
* **Diagnostic Actions**: Checks processes via `psutil`, pings Redis connection, queries WhatsApp engine `/health` endpoint.
* **Runtime Verification**: Diagnostics successfully retrieve stats: CPU, memory, disk, PG state, Redis latency (0ms), Celery workers heartbeat.

### 2.8 [Emergency Lock] Settings
* **Flow**: Admin clicks Lock System → `POST /api/v1/admin/system/emergency-lock` (or `/emergency-unlock`) → Redis key updated → Client requests blocked.
* **Backend Endpoints**: `emergency_lock_system()` and `emergency_unlock_system()`
* **Redis Key Commit**: Sets string key `emergency_system_lock` to `"true"`.
* **Tenant Blockage Guard**: Middleware `get_current_user` asserts that if lockdown is active, all requests raise `503 Service Unavailable`. Admin accounts are whitelisted to bypass this blockade.
* **Runtime Verification**: Verified Redis key and tenant access blockages during locked states.
