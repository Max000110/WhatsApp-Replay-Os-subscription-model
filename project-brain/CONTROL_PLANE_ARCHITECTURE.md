# ReplyOS — Control Plane Architecture

This document describes the end-to-end routing, transactional boundary guarantees, and components of the Super Admin Control Plane.

---

## 1. Request Flow & Communication Model

When the Super Admin triggers an action inside the `/admin` interface, the payload navigates through the following network architecture:

```
        Next.js UI Component (`frontend/src/app/admin/page.tsx`)
                              │ (Triggers ApiClient helper)
                              ▼
           API Client Wrapper (`frontend/src/lib/api.ts`)
                              │ (Sends request with bearer token)
                              ▼
           Nginx Reverse Proxy (`nginx/default.conf`)
                              │ (Matches `/api/v1` prefix)
                              ▼
           FastAPI Admin Router (`backend/app/routers/admin.py`)
                              │ (Validates JWT claims & role scopes)
               ┌──────────────┴──────────────┐
               ▼                             ▼
       Redis (MFA / Lock)           Postgres Database (SQL ORM)
   - Checks lockdown state       - Executes SQL transaction
   - Manages brute lockout       - Writes admin audit logs
```

---

## 2. Transactional Guarantees & ACID Safety

All write actions executed from the Super Admin Control Plane are protected by transaction boundaries to prevent inconsistent database state:

### 2.1 Database Commit Blocks
* Inside the backend controllers, queries are executed inside atomic SQLAlchemy session blocks. 
* Example: Tenant suspension writes changes to multiple tables (`tenants`, `users`, and `subscriptions`) inside a single block:
  ```python
  tenant.status = "suspended"
  for u in users:
      u.is_active = False
  if sub:
      sub.status = "suspended"
  db.commit()
  ```
* **Safety rollback**: If any SQL query fails, the session runs `db.rollback()`. This prevents orphaned records (e.g., suspending a subscription but leaving associated users active).

### 2.2 Async Integration Boundaries
* Operations that interact with external networks (like calling the Node.js WhatsApp Engine to sever companion sockets) are conducted **outside** the main SQL commit block.
* If the Node.js engine is offline or times out, the backend logs a warning and proceeds with database mutations, preventing database locks or API hangs from external network latency.

---

## 3. Platform Circuit Breaker (Lockdown)

The Global Emergency Lock is managed in Redis to ensure high-performance, single-instance verification:
* **Activation**: Setting the lock sets Redis key `emergency_system_lock = "true"`.
* **Enforcement**: FastAPI authentication helper `get_current_user` intercepts incoming customer API requests and raises a `503 Service Unavailable` error if the key is active.
* **Bypass exception**: Users with `role == "admin"` bypass the lock to allow administrative control and access to `/admin` for troubleshooting.
