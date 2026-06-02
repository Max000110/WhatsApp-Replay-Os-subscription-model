# Service Termination System Specification

This document describes the design, database attributes, service workflows, and validation sequences of the **ReplyOS Service Termination System**.

---

## 1. Dynamic Modes of Termination

The control plane implements two distinct modes of service termination:

### Mode 1 — Instant Termination
* **Objective**: Instantly lock out a hostile, fraudulent, or non-compliant tenant and sever all communication lines.
* **Execution Flow**:
  1. Sets `Tenant.status = "TERMINATED"`.
  2. Blocks all user logins immediately (`User.is_active = False` for all accounts).
  3. Pauses active marketing campaigns and silences AI auto-replies.
  4. Triggers asynchronous WhatsApp API disconnects (`DELETE /sessions/{sess_id}`) to close session websockets in the Baileys engine.
  5. Suspends subscription billing.
  6. If `data_retention_policy` is `"delete"`, it immediately invokes a secure transactional hard purge.

### Mode 2 — Graceful Termination
* **Objective**: Terminate a tenant due to natural subscription expirations or voluntary accounts cancellation, providing a standard compliance grace period.
* **Execution Flow**:
  1. Sets `Tenant.status = "PENDING TERMINATION"`.
  2. Sets `Tenant.termination_grace_period_ends = datetime.utcnow() + timedelta(hours=24)`.
  3. Dispatches high-priority warning alerts over WebSockets to client dashboards.
  4. Keeps chatbot auto-replies, campaign managers, and API calls active during the 24-hour window, enabling data export.
  5. After 24 hours, the Celery background daemon (`check_graceful_terminations_task`) executes, changes status to `TERMINATED`, blocks logins, kills WhatsApp sessions, and triggers data deletes if configured.

---

## 2. Technical Implementation Blueprints

```text
       Super Admin Portal (POST /admin/tenants/{id}/terminate)
                                  |
            +---------------------+---------------------+
            |                                           |
     [Mode: Instant]                             [Mode: Graceful]
            |                                           |
            v                                           v
    Update Tenant Status                        Update Tenant Status
      to TERMINATED                               to PENDING TERMINATION
            |                                   Set termination_grace_period_ends
            v                                           |
   Deactivate Users,                                    v
  Kill Active Sessions,                        Broadcast WebSocket Alert:
  Suspend Subscription                         "Scheduled for delete in 24h"
            |                                           |
            v                                           v
  Data Policy: Delete?                           Allow data export
    |                |                          during grace period
   Yes               No                                 |
    |                |                                  v
    v                v                           Celery periodic task
 Hard Purge      Archive                        validates grace period expiry
                                                        |
                                                        v
                                              Transition to TERMINATED
                                              (Execute Lockout & Purge)
```

### 2.1 Backend Router Controllers (`backend/app/routers/admin.py`)
Guarded by `get_current_super_admin`, enforcing strict RBAC verification and 2FA credentials check. When a termination event is commanded, the router updates database values and executes instant disconnects.

### 2.2 Celery Background Daemon (`backend/worker/tasks.py`)
Processes graceful terminations. Running periodically, it queries:
```sql
SELECT * FROM tenants 
WHERE status = 'PENDING TERMINATION' 
  AND termination_grace_period_ends <= NOW();
```
For every matching tenant, it updates their status to `"TERMINATED"`, locks all tenant user accounts (`is_active = False`), disconnects WhatsApp sessions from the engine, and performs hard deletes if the policy is set to `"delete"`.

### 2.3 WhatsApp Engine Disconnection
During terminations, the backend sends a DELETE request to the WhatsApp Engine:
```http
DELETE /sessions/{sess_id}
```
This commands Baileys to close socket connections, clean up authentication data folders, and release resources.

---

## 3. Data Purging & Retention Cleanup

When data purging is triggered, the system executes an atomic transaction block inside PostgreSQL:
```python
# 1. Clean local physical filesystem files
kb_docs = db.query(KBDocument).join(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
for doc in kb_docs:
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

# 2. Database Cascading Purge
db.delete(tenant)
db.commit()
```
This is incredibly robust and clean, as all related tables cascade delete automatically.

---

## 4. Verification Sequences

To verify the termination system:
1. Trigger a graceful termination:
   ```bash
    curl -X POST http://144.24.126.153:8080/api/v1/admin/tenants/{tenant_id}/terminate \
     -H "Authorization: Bearer <super_admin_jwt>" \
     -H "Content-Type: application/json" \
     -d '{"mode": "graceful"}'
   ```
2. Verify that the client receives WebSocket warnings and status in DB is `PENDING TERMINATION`.
3. Fast-forward the expiration or trigger manually using the Manual Cron Trigger endpoint `/api/v1/admin/system/trigger-cron`.
4. Verify that the tenant status changes to `TERMINATED`, all user accounts become `is_active = false`, and active WhatsApp sessions disconnect.
