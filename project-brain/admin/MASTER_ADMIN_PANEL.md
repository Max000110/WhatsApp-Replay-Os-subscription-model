# Master Admin Control Panel Blueprint

This document details the Super Admin system, routing endpoints, capabilities, and tenant management operations for administrators.

---

## 1. Authentication & Security Guardrails

The admin endpoints are mounted under `/api/v1/admin/*` and secured using a two-step dependency gate:
1. **Bearer Token Verification**: FastAPI `get_current_user` extracts the JWT token, verifies signatures, and pulls the database user context.
2. **Claims Assertion**: The `get_current_admin` helper dependency asserts the user's role field:
   ```python
   if current_user.role != "admin":
       raise HTTPException(status_code=403, detail="Requires Super Admin permissions.")
   ```

---

## 2. API Route Catalog

The following endpoints are defined in `backend/app/routers/admin.py`:

### A. Tenant Audit & Directory
* **Route**: `GET /api/v1/admin/tenants`
* **Response**: Returns a list of all tenants, user counts, subscription plan tier/status details, and active WhatsApp sessions metadata.

### B. Subscription Overrides & Plan Updates
* **Route**: `POST /api/v1/admin/tenants/{tenant_id}/activate`
  - Action: Manually activates or unlocks a tenant's plan.
* **Route**: `POST /api/v1/admin/tenants/{tenant_id}/suspend`
  - Action: Suspends the tenant's subscription and deactivates all user accounts mapped to that workspace.
* **Route**: `POST /api/v1/admin/tenants/{tenant_id}/change-plan`
  - Body: `{ "plan_tier": "pro", "max_bots": 5, "max_messages": 50000, "days": 30 }`
  - Action: Manually changes a tenant's subscription plan tier and resets active limits.

### C. System Telemetry & Log Monitoring
* **Route**: `GET /api/v1/admin/usage`
  - Stats: Total global messages sent, avg AI latency times, and token usage counts.
* **Route**: `GET /api/v1/admin/payments`
  - List: All captured and failed payment transaction records.
* **Route**: `GET /api/v1/admin/system-health`
  - CPU/RAM/Disk metrics of the host machine and online health logs of the WhatsApp Engine.

### D. Global Maintenance Alerts
* **Route**: `POST /api/v1/admin/broadcast-maintenance`
  - Body: `{ "message": "Scheduled DB maintenance at 2:00 AM UTC." }`
  - Action: Broadcasts a live alert banner to all active tenant WebSocket dashboard screens.

---

## 3. Operations Commands Reference

### Manually Promote a User to Admin
To elevate a tenant user to super admin via Postgres shell:
```sql
UPDATE users SET role = 'admin' WHERE email = 'admin@yourdomain.com';
```

### Broadcast a Maintenance Alert via curl
```bash
curl -X POST http://localhost:8080/api/v1/admin/broadcast-maintenance \
  -H "Authorization: Bearer <ADMIN-JWT-TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"message": "ReplyOS is undergoing database upgrades. Real-time updates might disconnect temporarily."}'
```
