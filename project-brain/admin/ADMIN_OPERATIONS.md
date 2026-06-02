# Admin Operations Hardening and Transactional Safety

This document specifies the database transaction guarantees, safety mitigations, and execution constraints applied to all control plane actions.

---

## 1. ACID Transaction Guarantees

All write operations triggered by the Super Admin Control Plane are wrapped in atomic database transaction blocks. In the event of a crash, network error, or downstream API timeout, the entire query rolls back to prevent inconsistent states.

### 1.1 Tenant Suspension & Reactivation
* **Transaction boundaries**: Inside `suspend_tenant` and `reactivate_tenant` endpoints, the changes are committed inside a single SQLAlchemy session block:
  ```python
  tenant.status = "suspended"
  for u in users:
      u.is_active = False
  if sub:
      sub.status = "suspended"
  db.commit()
  ```
* **Safety guarantee**: If `db.commit()` fails or any query raises an exception, the SQL transaction rolls back. Users are never left active when the subscription is suspended.

### 1.2 Tenant Termination and Purge
* **Mode 1 (Instant Termination)**:
  1. Deletes physical uploads (PDF documents, text manuals) from local directory storage (`os.remove`).
  2. ORM cascading executes a single database transaction deleting the primary `tenants` record.
  3. Cascading foreign keys instantly wipe user accounts, sessions, conversations, messages, chatbots, campaigns, and vectors.
  4. Connection queues and session caches are cleared in Redis.
* **Transaction boundary**: Downstream WhatsApp Node engine session deletions are performed *asynchronously* or *outside* the SQL commit block. If the Node engine fails to respond, the database purge still completes cleanly, avoiding database lockouts or hangs on external network latency.

---

## 2. Platform Emergency Controls

The platform emergency lock system acts as a circuit breaker.

```
Incoming Request (Client Portal / API)
                │
     get_current_user Dependency
                │
  Reads 'emergency_system_lock' in Redis
  Is it set to "true"?
         ├── Yes ── Is user Super Admin?
         │             ├── Yes ── Allow request through
         │             └── No  ── Raise 503 Service Unavailable
         │
         └── No   ── Allow request through (normal checks)
```

### 2.1 Bypass Exceptions
Super Administrators (`user.role == "admin"`) are explicitly excluded from the lockdown block. This allows admins to access the Control Plane `/admin` to troubleshoot and toggle the emergency lock off.
