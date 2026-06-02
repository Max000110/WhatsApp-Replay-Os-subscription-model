# ReplyOS — Super Admin Architecture

This document describes the design architecture, functional tabs, and API endpoints of the Super Admin Control Plane.

---

## 1. System Layout & Interfaces

The Super Admin interface `/admin` is designed as a unified, responsive operations center structured into 5 tabs:

```
+-------------------------------------------------------------+
|                   REPLYOS CONTROL PLANE                     |
+-------------------------------------------------------------+
| Tab 1: Tenant Lifecycle Registry                            |
|        - Plan edits, renewals, suspensions, terminations    |
+-------------------------------------------------------------+
| Tab 2: System Real-time Diagnostics                         |
|        - VM CPU/RAM/Disk stats & Service heartbeats         |
+-------------------------------------------------------------+
| Tab 3: Permanent Administrative Audit                       |
|        - Read-only transactional audit trail                |
+-------------------------------------------------------------+
| Tab 4: Control Plane Hardening & Lock                       |
|        - TOTP 2FA configuration & Emergency Lockdown        |
+-------------------------------------------------------------+
| Tab 5: Profile & Password settings                          |
|        - Email updates & password rotation controls         |
+-------------------------------------------------------------+
```

---

## 2. API Router Endpoints (`routers/admin.py`)

Every operation in the control plane calls a validated administrative route:

| Tab | Action Description | HTTP Method | API Path | DB / System Mutation |
| :--- | :--- | :--- | :--- | :--- |
| **Tab 1** | Get Tenants list | `GET` | `/admin/tenants` | Fetches tenants, usage, and session stats |
| **Tab 1** | Edit Tenant Plan | `POST` | `/admin/tenants/{id}/change-plan` | Updates plan in `subscriptions` table |
| **Tab 1** | Suspend Tenant | `POST` | `/admin/tenants/{id}/suspend` | Sets status = `"suspended"` |
| **Tab 1** | Reactivate/Restore | `POST` | `/admin/tenants/{id}/reactivate` | Sets status = `"active"` |
| **Tab 1** | Set Quotas | `POST` | `/admin/tenants/{id}/quotas` | Modifies bot & messages monthly caps |
| **Tab 1** | Reset usage counters | `POST` | `/admin/tenants/{id}/reset-usage` | Purges message counts for current month |
| **Tab 1** | Terminate Tenant | `POST` | `/admin/tenants/{id}/terminate` | Cascading database deletion of tenant |
| **Tab 1** | Revoke Session | `POST` | `/admin/tenants/{id}/revoke-sessions` | Closes and removes Baileys session |
| **Tab 1** | Grant Access | `POST` | `/admin/tenants/{id}/grant-access` | Sets user `is_active = True` |
| **Tab 1** | Revoke Access | `POST` | `/admin/tenants/{id}/revoke-access` | Sets user `is_active = False` |
| **Tab 2** | Get Diagnostics | `GET` | `/admin/system-health` | Computes CPU/RAM/Disk and service pings |
| **Tab 2** | Get Storage Report | `GET` | `/admin/storage-report` | Resolves VM disk bytes and log folders size |
| **Tab 3** | Read Audit Logs | `GET` | `/admin/audit-logs` | Reads from `audit_logs` table |
| **Tab 4** | Emergency Lock | `POST` | `/admin/system/emergency-lock` | Sets `emergency_system_lock = "true"` in Redis |
| **Tab 4** | Emergency Unlock | `POST` | `/admin/system/emergency-unlock`| Deletes lock key from Redis |
| **Tab 4** | TOTP Setup | `POST` | `/admin/auth/totp/setup` | Generates 2FA QR code URI |
| **Tab 4** | TOTP Enable | `POST` | `/admin/auth/totp/enable` | Activates TOTP challenge enforcement |
| **Tab 4** | TOTP Disable | `POST` | `/admin/auth/totp/disable` | Deactivates TOTP requirements |

---

## 3. Telemetry Ingestion Pipeline

System health status calculations are resolved in the backend without mock metrics:
1. **Host Telemetry**: Gathers VM CPU, memory, and disk partition stats using `psutil`.
2. **Database Health**: Queries Postgres using SQLAlchemy `text("SELECT 1")` to verify connection response.
3. **Redis Latency**: Measures command execution round-trip latency (`ping()`) over the Redis broker URL.
4. **Celery Worker Ping**: Inspects worker nodes dynamically over the Redis broker: `celery.control.inspect().ping()`.
5. **WhatsApp Engine**: Sends a lightweight HTTP query to the companion Node manager to retrieve active sockets count.

---

## 4. Administrative Security Audit Logging

All write operations trigger the `log_audit()` wrapper which transactionally commits actions:
* **Table**: `audit_logs`
* **Properties recorded**: Timestamp, administrator ID, action types (`SUSPEND_TENANT`, `CHANGE_PLAN`, etc.), target tenant name, affected resources, and a JSON payload detailing state changes.
* **Safety constraint**: `admin_user_id` is set as nullable, allowing system-level blocks (e.g. brute-force locking) to resolve cleanly without SQL Integrity exceptions.
